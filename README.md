<p align="center">
  <img src="assets/demo.gif" width="720" height="405" />
</p>

Fast MOT is a real-time implementation of Deep Sort. The original Deep Sort cannot run in real-time on edge devices. 
  - [x] Efficient SSD detector
  - [x] Improve small object detection with Tiling
  - [x] OSNet for accurate REID
  - [x] Optical flow tracking and camera motion compensation
  - [ ] Replace SSD with YOLO V4
  
Fast MOT has an input size of 1280 x 720. Note that larger videos will be resized, which results in a drop in frame rate. It also assumes medium/small targets and cannot detect up close targets properly due to tiling. This repo uses a pretrained OSNet from [Torchreid](https://github.com/KaiyangZhou/deep-person-reid). Currently, tracking targets other than pedestrians will work but retraining OSNet on other classes can improve accuracy.  Tracking is tested with the MOT17 dataset on Jetson Xavier NX. The frame rate can reach 15 - 30 FPS depending on crowd density.

| # targets  | FPS on Xavier NX |
| ------------- | ------------- |
| 0 - 20  | 30  |
| 20 - 30  | 23  |
| 30 - 50  | 15  |

### Dependencies
- OpenCV (With Gstreamer)
- Numpy
- Numba
- Scipy
- PyCuda
- TensorRT (>=6)
- cython-bbox

#### Install for Jetson (TX2/Xavier NX/Xavier)
Install OpenCV, CUDA, and TensorRT from [NVIDIA JetPack](https://developer.nvidia.com/embedded/jetpack)    
  ```
  $ sh install_jetson.sh
  ```
#### Install for x86 (Not tested)
Make sure to have CUDA and TensorRT installed and build OpenCV from source with Gstreamer
  ```
  $ pip3 install -r requirements.txt
  $ cd fast_mot/models
  $ sh prepare_calib_data.sh
  ```

### Run tracking
- With camera (/dev/video0): 
  ```
  $ python3 app.py --mot
  ```
- Input video: 
  ```
  $ python3 app.py --input your_video.mp4 --mot
  ```
- Use `--gui` to visualize and `--output video_out.mp4` to save output
- For more flexibility, edit `fast_mot/configs/mot.json` to configure parameters and target classes (COCO)
