import bpy
import numpy as np

import blendtorch.btb as btb

import math
import mathutils
import os
import sys
import random
from mathutils import Vector, Matrix, Euler

def rotate_eye(obj, x_angle, z_angle):
    obj.rotation_mode = 'XYZ'
    deg_to_rad = np.pi * 2/360
    x_rot = -x_angle * deg_to_rad
    z_rot = z_angle * deg_to_rad
    euler_rotation =  Euler((x_rot, 0, z_rot) , 'XYZ')
    obj.rotation_euler = euler_rotation
    outer_eye.rotation_euler = Euler((-x_rot - np.pi/2, 0, z_rot) , 'XYZ')
    obj_rot_mat = euler_rotation.to_matrix()
    
    #obj_rot_mat = initPoseMat

    if obj.parent:
        P = obj.parent.matrix.decompose()[1].to_matrix()
        obj_rot_mat = P * obj_rot_mat * P.inverted()

scene = bpy.context.scene
armature = bpy.data.objects['Armature Head']
camera_obj = bpy.data.objects['Camera']
camera = bpy.data.cameras['Camera']


eyeLbone = armature.pose.bones['def_eye.L']
eyeLblinkbone = armature.pose.bones['eyeblink.L']
eyeRbone = armature.pose.bones['def_eye.R']
eyeRblinkbone = armature.pose.bones['eyeblink.R']

outer_eye = bpy.data.collections["Collection 1"].objects['eye-outer']

armature_matrix = armature.matrix_world


def main():
    # Parse script arguments passed via blendtorch launcher
    btargs, remainder = btb.parse_blendtorch_args()

    cam = bpy.context.scene.camera
    

    def pre_frame():
        # Called before processing a frame
        #set the parameters here
        
        elev = 0
        azim = 15
        
        input_eye_closedness = 0.0

        z_angle = -azim
        x_angle = -elev

        for c in list(eyeLbone.constraints.values()):
            eyeLbone.constraints.remove(c)
        for c in list(eyeRbone.constraints.values()):
            eyeRbone.constraints.remove(c)

        # # Set eye target

        rotate_eye(eyeLbone, x_angle, z_angle)

        # # Set eye blink location
        eyeLblinkbone.location[2] = input_eye_closedness * eyeLblinkbone.constraints['Limit Location'].max_z   
        eyeRblinkbone.location[2] = input_eye_closedness * eyeRblinkbone.constraints['Limit Location'].max_z 
        
    def post_frame(off, pub, anim, cam):
        # Called every after Blender finished processing a frame.
        # Will be sent to one of the remote dataset listener connected.
        pub.publish(
            image=off.render(), 
#             xy=cam.object_to_pixel(cube), 
            frameid=anim.frameid
        )

    # Data source
    pub = btb.DataPublisher(btargs.btsockets['DATA'], btargs.btid)

    # Setup default image rendering
    cam = btb.Camera()
    off = btb.OffScreenRenderer(camera=cam, mode='rgb')
    off.set_render_style(shading='RENDERED', overlays=False)

    # Setup the animation and run endlessly
    anim = btb.AnimationController()
    anim.pre_frame.add(pre_frame)
    anim.post_frame.add(post_frame, off, pub, anim, cam)    
    anim.play(frame_range=(0,100), num_episodes=-1, use_animation=False)

main()