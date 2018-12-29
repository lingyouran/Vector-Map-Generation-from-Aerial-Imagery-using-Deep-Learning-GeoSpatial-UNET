from __future__ import print_function
from src import loss, io, log
# from matplotlib import pyplot as plt
from keras.models import load_model
import os
import sys
from keras.models import Model
from keras import backend as K
import cv2
import numpy as np
import time as mtime
import argparse
# import logging
from src.io import checkdir
from src import postprocess
import gdal

# Setup logging
# logger = log.get_logger('testing')
# logger.propagate = False
# log.log2file('Testing')

parser = argparse.ArgumentParser(
    description='See description below to see all available options')

parser.add_argument('-d', '--data',
                    help='Input directory containing image and label',
                    required=True)

parser.add_argument('-s', '--size', type=int,
                    help='Input size of image to be used. [Default] = 200',
                    default=200,
                    required=False)

parser.add_argument('-sg', '--skip_gridding', type=int,
                    help='If gridding is already done then skip it. [Default] is 0 (No)',
                    default=0,
                    required=False)

parser.add_argument('-m', '--model',
                    help='Input pre-trained model file',
                    required=True)

parser.add_argument('-m_cpu', '--max_cpu', type=float,
                    help='Maximum number of images in RAM at once. [Default] is = 50000.00',
                    default=50000.00,
                    required=False)

parser.add_argument('-m_gpu', '--max_gpu', type=float,
                    help='Maximum number of image in GPU at once. [Default] is = 6500.00',
                    default=6500.00,
                    required=False)

parser.add_argument('-g_tile', '--grid_size', type=int,
                    help='Size of gridding tiles. [Default] is = 200',
                    default=200,
                    required=False)

parser.add_argument('-op', '--overlap', type=int,
                    help='Overlap percentage when gridding. [Default] is = 0',
                    default=0,
                    required=False)

parser.add_argument('-f', '--format', type=str,
                    help=' Specify the output format of the results. Available options are shp, geojson, kml. [Default] = shp',
                    default='shp',
                    required=False)

parser.add_argument('-lf', '--linearfeature', type=int,
                    help='If data is linear feature. Example in case of road and railways. [Defualt] is 0 (no)',
                    default=0,
                    required=False)


# Parsing arguments
args = parser.parse_args()
path_data = args.data
image_size = args.size
skip_gridding = args.skip_gridding
path_model = args.model
grid_size = args.grid_size
max_num_cpu = args.max_cpu
max_num_gpu = args.max_gpu
percent_overlap = args.overlap
output_format = args.format
linear_feature = args.linearfeature

print('percent_overlap : ' + str(percent_overlap))
st_time = mtime.time()

# Storing time of process here
timing = {}

# Current running process
current_process = []
current_process.append('initilization')

# Filer for post processing
filter = 3
simplify_para = 0.7  # in metres

# input data
path_image = os.path.join(path_data, 'image')

# Results path
path_result = os.path.join(path_data, 'result')
path_tiled = os.path.join(path_result, 'tiled')
path_predict = os.path.join(path_result, 'prediction')
path_merged_prediction = os.path.join(path_result, 'merged_prediction')

# Tiled path
path_tile_image = os.path.join(path_tiled, 'image')

# Output file
file_output = os.path.join(path_merged_prediction, 'output.tif')

# Logging output paths
print('Tile image path is %s' % (path_merged_prediction))
print('Tile image path is %s' % (path_tile_image))
print('Predict path is %s' % (path_predict))
print('Result path is %s' % (path_result))
print('Image path is %s' % (path_image))


print('Tiling Images ...')

# Creating directory
checkdir(path_tile_image)
checkdir(path_predict)
checkdir(path_tiled)
checkdir(path_data)
checkdir(path_merged_prediction)

if skip_gridding == 0:
    time = mtime.time()
    current_process.append('tiling')
    tile_image = io.checkres(path_image, grid_size,
                             path_tile_image, percent_overlap)
    timing[current_process[-1]] = mtime.time() - time
print('Tiling Completed')


# load all the training images
train_set = io.train_data()

# Definging inputs to the class
train_set.path_image = path_tile_image
train_set.path_label = path_tile_image

train_set.image_size = grid_size
train_set.max_num_cpu = max_num_cpu
train_set.max_num_gpu = max_num_gpu

# Listing images
train_set.list_data()
part = len(train_set.image_part_list)

for k in range(part):
    # Loading the training image and labeled image
    current_process.append('loading_images')
    train_image = io.get_image(
        train_set.image_part_list[k], train_set.image_size)

    shape_train_image = train_image.shape

    # Printing type and number of imgaes and labels
    print("shape of train_image" + str(shape_train_image))

    train_image = np.resize(train_image, [
                            shape_train_image[0], shape_train_image[1], shape_train_image[2], 3])

    # get name,size,geo referencing data
    data = io.get_geodata(train_set.image_part_list[k])

    # defining loss functions
    loss_ = loss.dice_coef_loss

    # loading model from model file not weights file
    model = load_model(path_model, custom_objects={
        'dice_coef_loss': loss.dice_coef_loss, 'dice_coef': loss.dice_coef, 'jaccard_coef': loss.jaccard_coef})
    current_process.append('loading_model')

    # prediction model
    predict_result = model.predict(
        train_image, batch_size=16, verbose=1)  # , steps=None)
    current_process.append('predicting')

    predict_image = []
    for i in range(predict_result.shape[0]):
        # im = train_images[i]
        lb = predict_result[i, :, :, :]
        lb = np.round(lb, decimals=0)
        path_im = os.path.join(path_predict, os.path.basename(data['name'][i]))
        predict_image.append(path_im)

        # Saving data to disk
        current_process.append('saving_prediction')
        io.write_tif(path_im, lb*255, data['geotransform']
                     [i], data['geoprojection'][i], data['size'][i])
        current_process.append('saving_prediction')

timing['Processing'] = mtime.time() - st_time


# Merging tiled dataset to single tif
time = mtime.time()
print('Merging and compressing %s tiled dataset. This may take a while' % (
    str(train_set.count)))
current_process.append('merging')
io.merge_tile(file_output, predict_image)

# merging completed
timing[current_process[-1]] = mtime.time() - time

# Post Processing output image
if linear_feature == 0:

    # Post processing erosion
    print('Post Processing erosion')
    current_process.append('erosion')
    time = mtime.time()

    path_erosion = os.path.join(path_merged_prediction, 'erosion.tif')
    file_output = postprocess.erosion(file_output, filter, path_erosion)

    # Erosion completed
    timing[current_process[-1]] = mtime.time() - time

    # Watershed segmentation
    neighbour = 4
    print('Post Processing watershed_segmentation')
    current_process.append('watershed_segmentation')
    time = mtime.time()
    path_watershed = os.path.join(path_merged_prediction, 'watershed.tif')
    file_output = postprocess.waterseg(file_output, neighbour, path_watershed)

    # Watershed segmentation completed
    timing[current_process[-1]] = mtime.time() - time

    # Converting raster to Vector
    time = mtime.time()
    print('Converting Raster to vector')
    current_process.append('vectorization')

    path_r2v = io.raster2vector(
        file_output, os.path.dirname(file_output), output_format)

    # Vectorization completed
    timing[current_process[-1]] = mtime.time() - time

    # Simplification of polygons
    path_simplify = os.path.join(path_merged_prediction, 'simplify.shp')
    postprocess.simplify_polygon(path_r2v, simplify_para, path_simplify)

    # Shp to axis aligned bounding box
    print('Post Processing bounding box')
    current_process.append('aabbox')
    time = mtime.time()

    path_bbox = os.path.join(path_merged_prediction, 'bbox.shp')
    postprocess.aabbox(path_r2v, path_bbox)

    # aabbox completed
    timing[current_process[-1]] = mtime.time() - time


elif linear_feature == 1:
    print('Post Processing skeletonization')
    current_process.append('skeletonization')
    time = mtime.time()

    path_skeleton = os.path.join(path_merged_prediction, 'skeleton.tif')
    _ = postprocess.skeletonize(file_output, path_skeleton)

    # Skeletonization completed
    timing[current_process[-1]] = mtime.time() - time

    # Converting raster to Vector
    time = mtime.time()
    print('Converting Raster to vector')
    path_r2v = io.raster2vector(
        file_output, os.path.dirname(file_output), output_format)

    # Vectorization completed
    timing[current_process[-1]] = mtime.time() - time


# Saving to JSON
io.tojson(timing, os.path.join(path_result, 'Timing.json'))

print('Process Completed')
sys.exit()
