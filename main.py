import argparse
import datetime
import ee
import io, os, sys
import matplotlib.pyplot as plt
from osgeo import gdal
import pandas as pd
from PIL import Image
import requests
import tempfile
import zipfile

parser = argparse.ArgumentParser(description = 'Create PNG and GIF from TROPOMI data')
parser.add_argument('--p', help='pollution type')
parser.add_argument('--s', help='start date')
parser.add_argument('--e', help='end date')
parser.add_argument('--o', help='output location')
parser.add_argument('--h', help='image height')
parser.add_argument('--w', help='image width')

args = parser.parse_args()

if None in [args.p, args.s, args.e, args.o, args.h, args.w]:
    print('One or more arguments are missing')
    sys.exit()

print('Initialising earthengine')
ee.Initialize()
print('Successful')

region = ee.Geometry.Polygon(
  [[[-179.99, -89.99],
      [179.99, -89.99],
      [179.99, 89.99],
      [-179.99, 89.99],
      [-179.99, -89.99]]],
  )
tempdir = tempfile.mkdtemp()

# create daily mean image
def dailyCol(col):
    distinctDate = col.distinct('TIME_REFERENCE_DAYS_SINCE_1950')
    filter = ee.Filter.equals(leftField='TIME_REFERENCE_DAYS_SINCE_1950', 
                              rightField='TIME_REFERENCE_DAYS_SINCE_1950')
    join = ee.Join.saveAll('date_matches')
    joinCol = ee.ImageCollection(join.apply(distinctDate, col, filter))

    def reducer(img):
        comp = ee.ImageCollection.fromImages(img.get('date_matches'))
        return comp.reduce(ee.Reducer.mean())
    
    reduced = joinCol.map(algorithm= reducer)
    return reduced

if args.p in ['SO2', 'so2']:
    imgCol = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_SO2').select('SO2_column_number_density')
elif args.p in ['NO2', 'no2']: 
    imgCol = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2').select('tropospheric_NO2_column_number_density')
else:
    print('please select either "SO2" or "NO2"')
# imgCol = imgCol.filterDate(args.s, args.e)

dates = pd.date_range(args.s, args.e, freq = 'D')

# download the images
for date in dates:
    tom = date + datetime.timedelta(days = 1)
    col = imgCol.filterDate(date.strftime('%Y-%m-%d'), tom.strftime('%Y-%m-%d'))
    reduced = dailyCol(col)
    url = reduced.first().clip(region).getDownloadURL()
    r = requests.get(url)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(tempdir)
    if args.p in ['SO2', 'so2']:
        os.rename(os.path.join(tempdir, 'download.SO2_column_number_density_mean.tif'), 
                  os.path.join(tempdir, date.strftime('%Y-%m-%d')+'.tif'))
    elif args.p in ['NO2', 'no2']: 
        os.rename(os.path.join(tempdir, 'download.tropospheric_NO2_column_number_density_mean.tif'), 
                  os.path.join(tempdir, date.strftime('%Y-%m-%d')+'.tif'))

# converting images into PNG
print('Exporting png files')

files = os.listdir(os.path.join(tempdir))

for file in files:
    dataset = gdal.Open(os.path.join(tempdir, file))
    band1 = dataset.GetRasterBand(1)
    b1 = band1.ReadAsArray()

    fig, ax = plt.subplots()
    fig.set_frameon(False)
    ax.axis('off')
    im = ax.imshow(b1)

    if args.p in ['SO2', 'so2']:
        im.set_clim(0, 0.001)
    elif args.p in ['NO2', 'no2']: 
        im.set_clim(0, 0.0001)

    im.axes.get_xaxis().set_visible(False)
    im.axes.get_yaxis().set_visible(False)
    fig.set_size_inches(int(args.w) / 72, int(args.h) / 72)
    plt.tight_layout()
    # fig.set_size_inches(5, 4)
    plt.savefig(os.path.join(args.o, file[:-4] + '.png'), dpi = 72)

# combine PNG together into GIF
print('Creating the gif')

files = os.listdir(args.o)

img = []

for file in files:
    image = Image.open(os.path.join(args.o, file))
    img.append(image)

img[0].save(os.path.join(args.o, args.s + '_' + args.e + '.gif'), 
            save_all = True, append_images = img[1:], duration = 200)

print('Finished!')
