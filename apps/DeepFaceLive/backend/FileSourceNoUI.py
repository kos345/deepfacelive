import time
from enum import IntEnum
from pathlib import Path

from xlib import player as lib_player
from xlib.image import ImageProcessor
from xlib.mp import csw as lib_csw

from .BackendBase import (BackendConnection, BackendConnectionData, BackendDB,
                          BackendHost, BackendWeakHeap, BackendWorker,
                          BackendWorkerState)


class InputType(IntEnum):
    IMAGE_SEQUENCE = 0
    VIDEO_FILE = 1


class FileSourceNoUI(BackendHost):
    def __init__(self, weak_heap: BackendWeakHeap,
                 bc_out: BackendConnection,
                 backend_db: BackendDB = None):
        super().__init__(backend_db=backend_db,
                         sheet_cls=Sheet,
                         worker_cls=FileSourceWorker,
                         worker_state_cls=WorkerState,
                         worker_start_args=[weak_heap, bc_out])


class FileSourceWorker(BackendWorker):
    def on_start(self, weak_heap: BackendWeakHeap, bc_out: BackendConnection):
        self.weak_heap = weak_heap
        self.bc_out = bc_out
        self.bcd_uid = 0
        self.pending_bcd = None
        self.fp = None  # Frame player instance

        state, cs = self.get_state(), self.get_control_sheet()

        # Initialize source type
        state.input_type = state.input_type or InputType.VIDEO_FILE

        # Setup frame processing
        if state.input_path:
            self._initialize_frame_player(state.input_path, state.input_type, state.target_width)

    def _initialize_frame_player(self, input_path: Path, input_type: InputType, target_width: int):
        """Initialize the frame player with given parameters"""
        try:
            # Create appropriate player based on input type
            if input_type == InputType.IMAGE_SEQUENCE:
                fp = lib_player.ImageSequencePlayer(input_path)
            else:  # VIDEO_FILE
                fp = lib_player.VideoFilePlayer(input_path)

            # Configure processing parameters
            if target_width is not None:
                fp.set_target_width(target_width)

            # Seek to first frame
            fp.req_frame_seek(0, 0)
            self.set_fp(fp)
            return True
        except Exception as e:
            self.get_control_sheet().error.set_error(str(e))
            return False

    def set_fp(self, fp):
        """Update frame player instance"""
        if self.fp != fp:
            if self.fp:
                self.fp.dispose()
            self.fp = fp

    def on_tick(self):
        """Main processing loop"""
        # Process frames if available
        if self.fp and self.pending_bcd is None:
            pr = self.fp.process()

            if pr.new_error:
                self.get_control_sheet().error.set_error(pr.new_error)

            if pr.new_frame:
                self._process_frame(pr.new_frame)

        # Send processed frame if ready
        if self.pending_bcd and not self.bc_out.is_full_read(1):
            self.bc_out.write(self.pending_bcd)
            self.pending_bcd = None

        time.sleep(0.001)

    def _process_frame(self, p_frame):
        """Process and prepare frame data for output"""
        self.bcd_uid += 1
        bcd = BackendConnectionData(uid=self.bcd_uid)

        # Configure connection data
        bcd.assign_weak_heap(self.weak_heap)
        bcd.set_frame_count(p_frame.frame_count)
        bcd.set_frame_num(p_frame.frame_num)
        bcd.set_frame_image_name(p_frame.name)

        # Process and attach image
        image = ImageProcessor(p_frame.image).to_uint8().get_image('HWC')
        bcd.set_image(p_frame.name, image)

        self.pending_bcd = bcd

    def on_stop(self):
        self.set_fp(None)


class WorkerState(BackendWorkerState):
    input_type: InputType = InputType.VIDEO_FILE
    input_path: Path = None
    target_width: int = None  # None = auto


# class Sheet:
#     class Host(lib_csw.Sheet.Host):
#         def __init__(self):
#             self.input_path = lib_csw.Paths.Client()
#             self.input_type = lib_csw.StaticSwitch.Client()
#             self.target_width = lib_csw.Number.Client()
#             self.error = lib_csw.Error.Client()
#
#     class Worker(lib_csw.Sheet.Worker):
#         def __init__(self):
#             self.input_path = lib_csw.Paths.Host()
#             self.input_type = lib_csw.StaticSwitch.Host()
#             self.target_width = lib_csw.Number.Host()
#             self.error = lib_csw.Error.Host()

class Sheet:
    class Host(lib_csw.Sheet.Host):
        def __init__(self):
            # ВАЖНО: Вызываем конструктор родительского класса
            super().__init__()

            # Используем Path вместо Paths для одиночного пути
            self.input_path = lib_csw.Paths.Client()
            # self.add_control(self.input_path)

            # self.input_type = lib_csw.StaticSwitch.Client()
            # self.add_control(self.input_type)

            self.target_width = lib_csw.Number.Client()
            # self.add_control(self.target_width)

    class Worker(lib_csw.Sheet.Worker):
        def __init__(self):
            # ВАЖНО: Вызываем конструктор родительского класса
            super().__init__()

            self.input_path = lib_csw.Paths.Host()
            # self.add_control(self.input_path)

            # self.input_type = lib_csw.StaticSwitch.Host()
            # self.add_control(self.input_type)

            self.target_width = lib_csw.Number.Host()
            # self.add_control(self.target_width)