import numpy as np
import bpy, gpu, bgl
import os, sys
try:
    import OpenGL as ogl
    try:
        from OpenGL.GL import glGetTexImage   # this fails in <=2020 versions of Python on OS X 11.x
    except ImportError:
        print('Drat, patching for Big Sur')
        from ctypes import util
        orig_util_find_library = util.find_library
        def new_util_find_library( name ):
            res = orig_util_find_library( name )
            if res: return res
            return '/System/Library/Frameworks/'+name+'.framework/'+name
        util.find_library = new_util_find_library
        from OpenGL.GL import glGetTexImage
except ImportError:
    pass

from .signal import Signal
from .camera import Camera
from .utils import find_first_view3d

class OffScreenRenderer:
    '''Provides offscreen scene rendering using Eevee.

    Rendering reusing the first found 3D Space View in Blender. The way this view
    is configured also defines how the resulting image looks like. Use the helper method
    `set_render_style` to adjust the appearance from within Python.

    This class' `render` method is expected to be called from a `POST_PIXEL` callback,
    which `AnimationController` takes care of. That is, invoking `render()` from 
    withing `post_frame` is considered save.
    
    Params
    ------
    camera: btb.Camera, None
        Camera view to be rendered. When None, default camera is used.
    origin: str
        When 'upper-left' flip the rendered data to match OpenCV image coordinate
        system. When 'lower-left' image is created using OpenGL coordinate system. Defaults to 'upper-left'.
    mode: str
        Defines the number of color channels. Either 'RGBA' or 'RGB'
    gamma_coeff: scalar, None
        When not None, applies gamma color correction to the rendered image.
        Blender performs offline rendering in linear color space that when 
        viewed directly appears to be darker than expected. Usually a value
        of 2.2 get's the job done. Defaults to None.

    Attributes
    -----------
    proj_matrix: Matrix
        Projection matrix to use. See `btb.camera` for helpers. Update this when
        the camera intrinsics change.
    view_matrix: Matrix
        View matrix to use. See `btb.camera` for helpers. Update this when
        the camera moves.
    '''
    
    def __init__(self, camera=None, mode='rgba', origin='upper-left', gamma_coeff=None):
        assert mode in ['rgba', 'rgb']
        assert origin in ['upper-left', 'lower-left']
        self.camera = camera or Camera()
        self.offscreen = gpu.types.GPUOffScreen(
            self.shape[1], 
            self.shape[0]
        )
        self.area, self.space, self.region = find_first_view3d()
        self.handle = None
        self.origin = origin
        self.gamma_coeff = gamma_coeff
        channels = 4 if mode=='rgba' else 3        
        self.buffer = np.zeros(
            (self.shape[0], self.shape[1], channels), 
            dtype=np.uint8
        )        
        self.mode = bgl.GL_RGBA if mode=='rgba' else bgl.GL_RGB

    @property
    def shape(self):
        return self.camera.shape

    def render(self):
        '''Render the scene and return image as buffer.
        
        Returns
        -------
        image: HxWxD array
            where D is 4 when `mode=='RGBA'` else 3.
        '''
        print("Start render")
        # switch on nodes
        bpy.context.scene.use_nodes = True
        tree = bpy.context.scene.node_tree
        links = tree.links
        
        # clear default nodes
        for n in tree.nodes:
            tree.nodes.remove(n)
        
        # create input render layer node
        rl = tree.nodes.new('CompositorNodeRLayers')      
        rl.location = 185,285
        
        # create output node
        v = tree.nodes.new('CompositorNodeViewer')   
        v.location = 750,210
        v.use_alpha = False
        
        # Links
        links.new(rl.outputs[0], v.inputs[0])  # link Image output to Viewer input
        logfile = 'blender_render.log'
        open(logfile, 'a').close()
        old = os.dup(1)
        sys.stdout.flush()
        os.close(1)
        os.open(logfile, os.O_WRONLY)

        # render
        bpy.context.scene.render.filepath = "~/render_eye"
        bpy.ops.render.render(write_still=True)

        os.close(1)
        os.dup(old)
        os.close(old)
                
        # get viewer pixels
        pixels = bpy.data.images['Viewer Node'].pixels
        print(len(pixels)) # size is always width * height * 4 (rgba)
        
        # copy buffer to numpy array for faster manipulation
        self.buffer = np.array(pixels[:]).reshape(self.shape[0], self.shape[1], 4)[:,:,:3]
        buffer = self.buffer
        if self.origin == 'upper-left':
            buffer = np.flipud(buffer)
        if self.gamma_coeff:
            buffer = self._color_correct(buffer, self.gamma_coeff)
        return buffer

    def set_render_style(self, shading='RENDERED', overlays=False):
        self.space.shading.type = shading
        self.space.overlay.show_overlays = overlays

    def _color_correct(self, buffer, coeff=2.2):
        ''''Return sRGB image.'''
        rgb = buffer[...,:3].astype(np.float32) / 255
        rgb = np.uint8(255.0 * rgb**(1/coeff))
        if buffer.shape[-1] == 4:
            return np.concatenate((rgb, buffer[...,3:4]), axis=-1)
        else:
            return rgb
