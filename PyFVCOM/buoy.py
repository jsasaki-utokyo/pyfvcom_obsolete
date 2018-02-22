"""
Functions to interrogate and extract buoy data from the buoys.db SQLite3
database.

"""

from __future__ import print_function

from datetime import datetime
from pathlib import Path
from warnings import warn

import numpy as np

try:
    import sqlite3
    use_sqlite = True
except ImportError:
    warn('No sqlite standard library found in this python '
         'installation. Some functions will be disabled.')
    use_sqlite = False


def _split_lines(line, remove_empty=False, remove_trailing=False):
    """
    Quick function to tidy up lines in an ASCII file (split on a given separator (default space)).

    Parameters
    ----------
    line : str
        String to split.
    remove_empty : bool, optional
        Set to True to remove empty columns. Defaults to leaving them in.
    remove_trailing : bool, optional
        Set to True to remove trailing empty columns. Defaults to leaving them in.

    Returns
    -------
    y : list
        The split string.

    """

    delimiters = (';', ',', '\t', ' ')
    delimiter = None
    for d in delimiters:
        if d in line:
            delimiter = d
            break

    # Clear out newlines.
    line = line.strip('\n')

    if remove_trailing:
        line = delimiter.join(line.rstrip(delimiter).split(delimiter))

    y = line.split(delimiter)

    if remove_empty:
        y = [i.strip() for i in line.split(delimiter) if i]

    return y


def get_buoy_metadata(db):
    """
    Extracts the meta data from the buoy database.

    Parameters
    ----------
    db : str
        Full path to the buoy data SQLite database.

    Returns
    -------
    meta_info : list
        List of dicts with keys based on the field names from the Stations
        table. Returns [False] if there is an error.

    """

    if not use_sqlite:
        raise RuntimeError('No sqlite standard library found in this python '
                           'installation. This function (get_buoy_metadata) '
                           'is unavailable.')

    def _dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    try:
        con = sqlite3.connect(db)

        con.row_factory = _dict_factory

        c = con.cursor()

        out = c.execute('SELECT * from Stations')

        meta_info = out.fetchall()

    except sqlite3.Error as e:
        if con:
            con.close()
            print('Error %s:' % e.args[0])
            meta_info = [False]

    finally:
        if con:
            con.close()

    return meta_info


def get_buoy_data(db, table, fields, noisy=False):
    """
    Extract the buoy from the SQLite database for a given site.  Specify the
    database (db), the table name (table) of the station of interest.

    Parameters
    ----------
    db : str
        Full path to the buoy data SQLite database.
    table : str
        Name of the table to be extracted (e.g. 'hastings_wavenet_site').
    fields : list
        List of names of fields to extract for the given table, such as
        ['Depth', 'Temperature']. Where no data exists, a column of NaNs will
        be returned (actually Nones, but numpy does the conversion for you).
    noisy : bool, optional
        Set to True to enable verbose output.

    Returns
    -------
    data : ndarray
        Array of the fields requested from the table specified.

    See Also
    --------
    buoy.get_observed_metadata : extract metadata for a buoy time series.

    Notes
    -----
    Search is case insensitive (b0737327 is equal to B0737327).

    """

    if not use_sqlite:
        raise RuntimeError('No sqlite standard library found in this python '
                           'installation. This function (get_buoy_data) is '
                           'unavailable.')

    if noisy:
        print('Getting data for {} from the database...'.format(table),
              end=' ')

    try:
        con = sqlite3.connect(db)

        with con:
            c = con.cursor()
            # I know, using a string is Bad. But it works and it's only me
            # working with this.
            c.execute('SELECT {} FROM {}'.format(','.join(fields), table))

            # Now get the data in a format we might actually want to use
            data = np.asarray(c.fetchall())

        if noisy:
            print('done.')

    except sqlite3.Error as e:
        if con:
            con.close()
            print('Error %s:' % e.args[0])
            data = np.asarray([False])

    finally:
        if con:
            con.close()

    return data.astype(float)


class Buoy:
    """ Generic class for buoy data (i.e. surface time series). """

    def __init__(self, filename, noisy=False):
        """
        Create a buoy object from the given file name.

        Parameters
        ----------
        filename : str, pathlib.Path
            The file name to read in.
        noisy : bool, optional
            If True, verbose output is printed to screen. Defaults to False.

        """

        self._file = Path(filename)

        self._debug = False
        self._noisy = noisy
        self._locations = None
        self._site = 'L4'
        self._time_header = ['Year', 'Serial', 'Jd', 'Time', 'Time_GMT', 'Date_YYMMDD', 'Time_HHMMSS', 'Date/Time_GMT']
        self.data = None
        self.position = None
        self.time = None

        # Get the metadata read in.
        self._slurp_file()
        self.header, self.header_length, self.header_indices = _read_header(self._lines, self._time_header)

    def _slurp_file(self):
        """
        Read in the contents of the file into self so we don't have to read each file multiple times.

        Provides
        --------
        self._lines : list
            The lines in the file, stripped of newlines and leading/trailing whitespace and split based on a trying a
            few common delimiters.

        """

        extension = self._file.suffix
        # Ignore crappy characters by forcing everything to ASCII.
        with self._file.open('r', encoding='ascii', errors='ignore') as f:
            empty = False
            trailing = False
            if extension == '.csv':
                # Probably CEFAS data which has empty columns, so we need to leave them in place. However, we need to
                # remove the trailing empty columns as the headers don't account for those.
                trailing = True
            elif extension == '.txt':
                # Probably WCO data, which is usually space separated, so nuke duplicate spaces.
                empty = True
            self._lines = f.readlines()
            self._lines = [_split_lines(i, remove_empty=empty, remove_trailing=trailing) for i in self._lines]

            # If we've left empty columns in, replace them with NaNs. This is not elegant.
            if not empty:
                new_lines = []
                for line in self._lines:
                    new_lines.append([np.nan if i == '' else i for i in line])
                self._lines = new_lines

    def load(self):
        """
        Parse the header and extract the data for the loaded file.

        Provides
        --------
        Adds data and time objects, with the variables and time loaded respectively. The time object also has a
        datetime attribute.

        """

        # Add times.
        self.time = self._ReadTime(self._lines)

        if not any(self.time.datetime):
            return

        # Add positions
        self.position = self._ReadPosition(self._locations, self._site)

        # Grab the data.
        self.data = self._ReadData(self._lines)

    class _Read(object):
        def __init__(self, lines, noisy=False):
            """
            Initialise parsing the buoy time series data so we can subclass this for the header and data reading.

            Parameters
            ----------
            lines : list
                The data to parse, read in by Buoys._slurp.
            noisy : bool, optional
                If True, verbose output is printed to screen. Defaults to False.

            Provides
            --------
            Attributes in self which are named for each variable found in `lines'. Each attribute contains a single
            time series as a numpy array.

            """

            self._debug = False
            self._noisy = noisy
            self._lines = lines
            self._time_header = ['Year', 'Serial', 'Jd', 'Time', 'Time_GMT', 'Date_YYMMDD', 'Time_HHMMSS', 'Date/Time_GMT']

            self._header, self._header_length, self._header_indices = _read_header(self._lines, self._time_header)
            self._read()

    class _ReadData(_Read):
        """ Read time series data from a given WCO file. This is meant to be called by the Buoy class. """

        def _read(self):
            """
            Parse the data in self._lines for each of the time series.

            Provides
            --------
            Attributes in self which are named for each variable found in `self._lines'. Each attribute contains a single
            time series as a numpy array.

            """

            # We want everything bar the time column names.
            num_lines = len(self._lines) - self._header_length
            num_columns = len(self._header)
            if num_lines > 1:
                for name in self._header:
                    if name not in self._time_header:
                        name_index = self._header_indices[name]
                        data = []
                        for line in self._lines[self._header_length:]:
                            # Only keep values where we've got as many columns as headers.
                            if len(line) == num_columns:
                                data.append(line[name_index])
                        setattr(self, name, np.asarray(data, dtype=float))

    class _ReadTime(_Read):
        """ Extract the time from the given WCO file. This is meant to be called by the Buoy class. """

        def _read(self):
            """
            Parse the data in self._lines for each of the time series.

            Provides
            --------
            Attributes in self which are named for each variable found in `self._lines'. Each attribute contains some
            time data. We also create a datetime attribute which has the times as datetime objects.

            """

            # Try everything in self._time_header values.
            self.time_header = []
            num_lines = len(self._lines) - self._header_length
            num_columns = len(self._header)
            if num_lines > 1:
                for name in self._header:
                    if name in self._time_header:
                        self.time_header.append(name)
                        name_index = self._header_indices[name]
                        data = []
                        for line in self._lines[self._header_length:]:
                            # Only keep values where we've got as many columns as headers.
                            if len(line) == num_columns:
                                data.append(line[name_index])
                        setattr(self, name, np.asarray(data))

            # Now make datetime objects from the time.
            self.datetime = []
            if hasattr(self, 'Year') and hasattr(self, 'Serial') and hasattr(self, 'Time'):
                # Western Channel Observatory data.
                for year, doy, time in zip(self.Year, self.Serial, self.Time):
                    self.datetime.append(datetime.strptime('{y}{doy} {hm}'.format(y=year, doy=doy, hm=time), '%Y%j %H.%M'))
            elif hasattr(self, 'Time (GMT)'):
                # CEFAS data
                for date in getattr(self, 'Time (GMT)'):
                    self.datetime.append(datetime.strptime(date, '%Y-%m-%d %H:%M:%S'))

    class _ReadPosition:
        """ Add the position for the buoy. """

        def __init__(self, location, site):
            """
            Grab the data for the given buoy site.

            Parameters
            ----------
            location : str, pathlib.Path
                File with the locations in (CSV).
            site : str
                The name of the site we're working on.

            Provides
            --------
            lon, lat : float
                The longitude and latitude of the site.

            """

            self.lon = 0
            self.lat = 0


def _read_header(lines, header_names):
    """
    Extract the header columns. Accounts for duplicates.

    Parameters
    ----------
    lines : list
        List of the lines from the file.
    header_names : list
        Header time variable names to search for which define the header.

    Returns
    -------
    header : list
        List of the header names.
    header_length : int
        Number of lines in the header.
    header_indices : dict
        Indices of each header name in `header' with the name as the key.

    """
    header_length = 0
    for count, line in enumerate(lines):
        if any(time in line for time in header_names):
            header_length = count
        else:
            break

    header_length += 1

    header = lines[header_length - 1]

    header_indices = {i: header.index(i) for i in header}

    return header, header_length, header_indices
