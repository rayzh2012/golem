import unittest
import os

from golem.resource.dirmanager import DirManager
from golem.tools.testdirfixture import TestDirFixture
from golem.tools.assertlogs import LogTestCase
from golem.task.taskbase import ComputeTaskDef

from gnr.renderingtaskstate import RenderingTaskDefinition
from gnr.task.luxrendertask import LuxRenderDefaults, LuxRenderTaskBuilder, LuxRenderOptions, logger


class TestLuxRenderDefaults(unittest.TestCase):
    def test_init(self):
        ld = LuxRenderDefaults()
        self.assertTrue(os.path.isfile(ld.main_program_file))


class TestLuxRenderTaskBuilder(TestDirFixture, LogTestCase):

    def test_luxtask(self):
        td = RenderingTaskDefinition()
        lro = LuxRenderOptions()
        td.renderer_options = lro
        lb = LuxRenderTaskBuilder("ABC", td, self.path)
        luxtask = lb.build()
        self.__after_test_errors(luxtask)
        self.__queries(luxtask)

    def __after_test_errors(self, luxtask):
        with self.assertLogs(logger, level="WARNING"):
            luxtask.after_test({}, self.path)
        open(os.path.join(self.path, "sth.flm"), 'w').close()
        luxtask.after_test({}, self.path)
        prev_dir = luxtask.root_path
        luxtask.root_path = "/dev/null/:errors?"
        with self.assertLogs(logger, level="WARNING"):
            luxtask.after_test({}, self.path)
        luxtask.root_path = prev_dir
        dir_manager = DirManager("ABC", self.path, tmp="luxtmp")
        luxtask.initialize(dir_manager)
        assert os.path.isfile(os.path.join(luxtask.tmp_dir, "test_result.flm"))

    def __queries(self, luxtask):
        luxtask.collected_file_names["xxyyzz"] = "xxyyzzfile"
        luxtask.collected_file_names["abcd"] = "abcdfile"
        ctd = luxtask.query_extra_data_for_final_flm()
        self.assertIsInstance(ctd, ComputeTaskDef)
        assert ctd.src_code is not None
        assert ctd.extra_data['output_flm'] == luxtask.output_file
        assert set(ctd.extra_data['flm_files']) == {"xxyyzzfile", "abcdfile"}






