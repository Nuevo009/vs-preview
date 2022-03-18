from __future__ import annotations

import ctypes
import logging
import vapoursynth as vs
from yaml import YAMLObject
from dataclasses import dataclass
from typing import Any, Mapping, cast

from PyQt5 import sip
from PyQt5.QtGui import QImage, QPixmap, QPainter

from .units import Frame, FrameInterval, Time, TimeInterval


core = vs.core


@dataclass
class VideoOutputNode():
    clip: vs.VideoNode
    alpha: vs.VideoNode | None


class VideoOutput(YAMLObject):
    yaml_tag = '!VideoOutput'
    vs_type = vs.VideoOutputTuple

    class Resizer:
        Bilinear = core.resize.Bilinear
        Bicubic = core.resize.Bicubic
        Point = core.resize.Point
        Lanczos = core.resize.Lanczos
        Spline16 = core.resize.Spline16
        Spline36 = core.resize.Spline36

    class Matrix:
        values = {
            0: 'rgb',
            1: '709',
            2: 'unspec',
            # 3: 'reserved',
            4: 'fcc',
            5: '470bg',
            6: '170m',
            7: '240m',
            8: 'ycgco',
            9: '2020ncl',
            10: '2020cl',
            # 11: 'reserved',
            12: 'chromancl',
            13: 'chromacl',
            14: 'ictcp',
        }

        RGB = values[0]
        BT709 = values[1]
        UNSPEC = values[2]
        BT470_BG = values[5]
        ST170_M = values[6]
        ST240_M = values[7]
        FCC = values[4]
        YCGCO = values[8]
        BT2020_NCL = values[9]
        BT2020_CL = values[10]
        CHROMA_CL = values[13]
        CHROMA_NCL = values[12]
        ICTCP = values[14]

    class Transfer:
        values = {
            # 0: 'reserved',
            1: '709',
            2: 'unspec',
            # 3: 'reserved',
            4: '470m',
            5: '470bg',
            6: '601',
            7: '240m',
            8: 'linear',
            9: 'log100',
            10: 'log316',
            11: 'xvycc',  # IEC 61966-2-4
            # 12: 'reserved',
            13: 'srgb',  # IEC 61966-2-1
            14: '2020_10',
            15: '2020_12',
            16: 'st2084',
            # 17: 'st428',  # not supported by zimg 2.8
            18: 'std-b67',
        }

        BT709 = values[1]
        UNSPEC = values[2]
        BT601 = values[6]
        LINEAR = values[8]
        BT2020_10 = values[14]
        BT2020_12 = values[15]
        ST240_M = values[7]
        BT470_M = values[4]
        BT470_BG = values[5]
        LOG_100 = values[9]
        LOG_316 = values[10]
        ST2084 = values[16]
        ARIB_B67 = values[18]
        SRGB = values[13]
        XV_YCC = values[11]
        IEC_61966_2_4 = XV_YCC
        IEC_61966_2_1 = SRGB

    class Primaries:
        values = {
            # 0: 'reserved',
            1: '709',
            2: 'unspec',
            # 3: 'reserved',
            4: '470m',
            5: '470bg',
            6: '170m',
            7: '240m',
            8: 'film',
            9: '2020',
            10: 'st428',  # or 'xyz'
            11: 'st431-2',
            12: 'st431-1',
            22: 'jedec-p22',
        }

        BT709 = values[1]
        UNSPEC = values[2]
        ST170_M = values[6]
        ST240_M = values[7]
        BT470_M = values[4]
        BT470_BG = values[5]
        FILM = values[8]
        BT2020 = values[9]
        ST428 = values[10]
        XYZ = ST428
        ST431_2 = values[11]
        ST431_1 = values[12]
        JEDEC_P22 = values[22]
        EBU3213_E = JEDEC_P22

    class Range:
        values = {
            0: 'full',
            1: 'limited'
        }

        LIMITED = values[1]
        FULL = values[0]

    class ChromaLoc:
        values = {
            0: 'left',
            1: 'center',
            2: 'top_left',
            3: 'top',
            4: 'bottom_left',
            5: 'bottom',
        }

        LEFT = values[0]
        CENTER = values[1]
        TOP_LEFT = values[2]
        TOP = values[3]
        BOTTOM_LEFT = values[4]
        BOTTOM = values[5]

    storable_attrs = (
        'name', 'last_showed_frame', 'play_fps',
        'frame_to_show', 'scening_lists'
    )
    __slots__ = storable_attrs + (
        'index', 'width', 'height', 'fps_num', 'fps_den',
        'total_frames', 'total_time', 'graphics_scene_item',
        'end_frame', 'end_time', 'fps', 'props', 'source', 'prepared',
        'main', 'checkerboard', '__weakref__', 'cur_frame'
        # hack to keep the reference to the current frame
    )

    source: VideoOutputNode
    prepared: VideoOutputNode
    format: vs.VideoFormat
    props: vs.FrameProps

    def clear(self) -> None:
        self.source = self.prepared = self.props = None  # type: ignore

    def __init__(self, vs_output: vs.VideoOutputTuple, index: int) -> None:
        from vspreview.widgets import GraphicsImageItem
        from vspreview.models import SceningLists
        from vspreview.utils import main_window

        self.main = main_window()

        # runtime attributes
        self.source = VideoOutputNode(vs_output.clip, vs_output.alpha)
        self.prepared = VideoOutputNode(vs_output.clip, vs_output.alpha)

        if self.source.alpha is not None:
            self.prepared.alpha = self.prepare_vs_output(self.source.alpha, True)

        self.index = index
        if not hasattr(core, 'libp2p'):
            print(Warning(
                "LibP2P is missing, it is reccomended to prepare output clips correctly!\n"
                "You can get it here: https://github.com/DJATOM/LibP2P-Vapoursynth"
            ))

        self.prepared.clip = self.prepare_vs_output(self.source.clip)
        self.width = self.prepared.clip.width
        self.height = self.prepared.clip.height
        self.props = self.source.clip.get_frame(0).props
        self.fps_num = self.prepared.clip.fps.numerator
        self.fps_den = self.prepared.clip.fps.denominator
        self.fps = self.fps_num / self.fps_den
        self.total_frames = FrameInterval(self.prepared.clip.num_frames)
        self.total_time = self.to_time_interval(self.total_frames - FrameInterval(1))
        self.end_frame = Frame(int(self.total_frames) - 1)
        self.end_time = self.to_time(self.end_frame)
        self.name = 'Video Node ' + str(self.index)

        if self.source.alpha:
            self.checkerboard = self._generate_checkerboard()

        # set by load_script() when it prepares graphics scene item based on last showed frame
        self.graphics_scene_item: GraphicsImageItem

        # storable attributes
        if 'Name' in self.props:
            self.name = 'Video Node %d: %s' % (index, cast(str, self.props['Name']))

        if (not hasattr(self, 'last_showed_frame') or self.last_showed_frame > self.end_frame):
            self.last_showed_frame: Frame = Frame(0)

        if not hasattr(self, 'scening_lists'):
            self.scening_lists: SceningLists = SceningLists()

        if not hasattr(self, 'play_fps'):
            self.play_fps = self.fps_num / self.fps_den

        if not hasattr(self, 'frame_to_show'):
            self.frame_to_show: Frame | None = None

    def prepare_vs_output(self, clip: vs.VideoNode, is_alpha: bool = False) -> vs.VideoNode:
        assert clip.format

        resizer = self.main.VS_OUTPUT_RESIZER
        resizer_kwargs = {
            'format': vs.RGB24,
            'matrix_in_s': self.main.VS_OUTPUT_MATRIX,
            'transfer_in_s': self.main.VS_OUTPUT_TRANSFER,
            'primaries_in_s': self.main.VS_OUTPUT_PRIMARIES,
            'range_in_s': self.main.VS_OUTPUT_RANGE,
            'chromaloc_in_s': self.main.VS_OUTPUT_CHROMALOC,
        }

        is_subsampled = (clip.format.subsampling_w != 0 or clip.format.subsampling_h != 0)

        if not is_subsampled:
            resizer = self.Resizer.Point

        if clip.format.color_family == vs.RGB:
            del resizer_kwargs['matrix_in_s']

        if is_alpha:
            if clip.format.id == vs.GRAY8:
                return clip
            resizer_kwargs['format'] = vs.GRAY8

        clip = resizer(clip, **resizer_kwargs, **self.main.VS_OUTPUT_RESIZER_KWARGS)

        if is_alpha:
            return clip

        if hasattr(core, 'libp2p'):
            return core.libp2p.Pack(clip)
        else:
            return core.akarin.Expr(
                core.std.SplitPlanes(clip),
                'x 0x100000 * y 0x400 * + z + 0xc0000000 +', vs.GRAY32, opt=1
            )

    def render_frame(self, frame: Frame) -> QPixmap:
        if self.prepared.alpha:
            return self.render_raw_videoframe(
                self.prepared.clip.get_frame(int(frame)),
                self.prepared.alpha.get_frame(int(frame))
            )
        else:
            return self.render_raw_videoframe(
                self.prepared.clip.get_frame(int(frame))
            )

    def render_raw_videoframe(
        self, vs_frame: vs.VideoFrame, vs_frame_alpha: vs.VideoFrame | None = None
    ) -> QPixmap:
        self.cur_frame = (vs_frame, vs_frame_alpha)  # keep a reference to the current frame

        stride_length = vs_frame.format.bytes_per_sample * vs_frame.width * vs_frame.height

        # powerful spell. do not touch
        frame_data_pointer = cast(
            sip.voidptr, ctypes.cast(vs_frame.get_read_ptr(0), ctypes.POINTER(ctypes.c_char * stride_length)).contents
        )
        frame_image = QImage(
            frame_data_pointer, vs_frame.width, vs_frame.height,
            vs_frame.get_stride(0), QImage.Format_RGB30
        )

        if vs_frame_alpha is None:
            return QPixmap.fromImage(frame_image)

        stride_length = vs_frame_alpha.format.bytes_per_sample * vs_frame_alpha.width * vs_frame_alpha.height

        alpha_data_pointer = cast(
            sip.voidptr, ctypes.cast(
                vs_frame_alpha.get_read_ptr(0), ctypes.POINTER(ctypes.c_char * stride_length)
            ).contents
        )

        alpha_image = QImage(
            alpha_data_pointer, vs_frame.width, vs_frame.height,
            vs_frame_alpha.get_stride(0), QImage.Format_Alpha8
        )

        result_image = QImage(vs_frame.width, vs_frame.height, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(result_image)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawImage(0, 0, frame_image)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, alpha_image)

        if self.main.CHECKERBOARD_ENABLED:
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
            painter.drawImage(0, 0, self.checkerboard)

        painter.end()

        return QPixmap.fromImage(result_image)

    def _generate_checkerboard(self) -> QImage:
        tile_size = self.main.CHECKERBOARD_TILE_SIZE
        tile_color_1 = self.main.CHECKERBOARD_TILE_COLOR_1
        tile_color_2 = self.main.CHECKERBOARD_TILE_COLOR_2

        macrotile_pixmap = QPixmap(tile_size * 2, tile_size * 2)
        painter = QPainter(macrotile_pixmap)
        painter.fillRect(macrotile_pixmap.rect(), tile_color_1)
        painter.fillRect(tile_size, 0, tile_size, tile_size, tile_color_2)
        painter.fillRect(0, tile_size, tile_size, tile_size, tile_color_2)
        painter.end()

        result_image = QImage(self.width, self.height, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(result_image)
        painter.drawTiledPixmap(result_image.rect(), macrotile_pixmap)
        painter.end()

        return result_image

    def _calculate_frame(self, seconds: float) -> int:
        return round(seconds * self.fps)

    def _calculate_seconds(self, frame_num: int) -> float:
        return frame_num / (self.fps or 1)

    def to_frame(self, time: Time) -> Frame:
        return Frame(self._calculate_frame(float(time)))

    def to_time(self, frame: Frame) -> Time:
        return Time(seconds=self._calculate_seconds(int(frame)))

    def to_frame_interval(self, time_interval: TimeInterval) -> FrameInterval:
        return FrameInterval(self._calculate_frame(float(time_interval)))

    def to_time_interval(self, frame_interval: FrameInterval) -> TimeInterval:
        return TimeInterval(seconds=self._calculate_seconds(int(frame_interval)))

    def __getstate__(self) -> Mapping[str, Any]:
        return {
            attr_name: getattr(self, attr_name)
            for attr_name in self.storable_attrs
        }

    def __setstate__(self, state: Mapping[str, Any]) -> None:
        from vspreview.models import SceningLists
        from vspreview.utils import try_load

        self.name = ''
        try_load(
            state, 'name', str, self.__setattr__,
            'Storage loading: Video Output: failed to parse name.'
        )

        self.last_showed_frame = Frame(0)
        try:
            try_load(
                state, 'last_showed_frame', Frame, self.__setattr__,
                'Storage loading: Video Output: failed to parse last showed frame.'
            )
        except IndexError:
            logging.warning('Storage loading: Video Output: last showed frame is out of range.')

        self.scening_lists = SceningLists()
        try_load(
            state, 'scening_lists', SceningLists, self.__setattr__,
            'Storage loading: Video Output: scening lists weren\'t parsed successfully.'
        )

        try:
            play_fps = state['play_fps']
            if not isinstance(play_fps, float):
                raise TypeError
            if play_fps > 0:
                self.play_fps = play_fps
        except (KeyError, TypeError):
            logging.warning('Storage loading: Video Output: play fps weren\'t parsed successfully.')
