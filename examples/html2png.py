import sys
import asyncio
import nest_asyncio
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page
# To avoid an error, the following should be invoked.
nest_asyncio.apply()

async def main(html_url, png_path=None, pdf_path=None, width=1920, height=1080, 
                   deviceScaleFactor=5, waitFor=3000, clip=None):
    '''
    Loading HTML (webpage) and exporting to PNG with specifying DPR using pyppetter
    Tested on Ubuntu 20.04 LTS on WSL2
    https://pyppeteer.github.io/pyppeteer/reference.html#browser-class
    https://miyakogi.github.io/pyppeteer/reference.html#page-class
    
    Parameters
    ----------
    html_url : str
        e.g.: "file:///home/teem/Github/pyfvcom/examples/png/example.html"
    out_path : str
        Output PNG path
    width : int, optional
        Viewport width or original image width (adjust in a trial and error manner)
    height : int, optional
        Viewport height or original image height (adjust in a trial and error manner)
    deviceScaleFactor : int, optional
        DPR (Device Pixel Ratio) = DPI/72. E.g., 5 corresponding to 360 DPI
    waitFor : int, optional
        Wait for function, timeout, or element which matches on page (milliseconds)
    clip : dict, optional
        Clipping area of the page
        {"x"(int): x-coordinate of top-left corner of clipping area, "y"(int): y-coordinate, 
         "width"(int): width of clipping area, "height"(int): height}
    '''

    browser = await launch(headless=True)
    page = await browser.newPage()

    await page.goto(html_url)
    # 'deviceScaleFactor' = DPR (Device Pixel Ratio) = DPI/72
    # 'hasTouch': True => Activates reloading browser page so that scaling (zooming) with
    #                     increasing resolution being implemented.
    await page.setViewport({'width': width, 'height': height,
                            'deviceScaleFactor': deviceScaleFactor,
                            'hasTouch': True})
    await page.waitFor(5000)
    #if png_path is not None:
    # await page.screenshot({'path': out_path, 'scale':1})
    await page.screenshot(path=png_path, scale=1, clip=clip)
    #if pdf_path is not None:
    #    await page.pdf(path=pdf_path, scale=1, width=width, height=height)
    await browser.close()

# Set PNG output file path
dirpath = "./png/"
core = "tri_sal_"
# Adjust width and height in a trial and error manner.
width=700; height=340
#for timestep in range(2):
timestep = int(sys.argv[1])
print(f"timestep={timestep}")
html_url = f"file:///home/teem/Github/pyfvcom/examples/png/{core}{timestep:03}.html"
png_path = f"{dirpath}{core}{timestep:03}.png"
print(f"png_path={png_path}")
print(f"html_url={html_url}")
asyncio.get_event_loop().run_until_complete(main(html_url, \
    png_path, width=width, height=height))
