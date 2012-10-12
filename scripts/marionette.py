#!/usr/bin/env python
# ***** BEGIN LICENSE BLOCK *****
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
# ***** END LICENSE BLOCK *****

import copy
import os
import re
import sys

# load modules from parent dir
sys.path.insert(1, os.path.dirname(sys.path[0]))

from mozharness.base.errors import PythonErrorList, TarErrorList
from mozharness.base.log import INFO, ERROR, OutputParser
from mozharness.base.script import BaseScript
from mozharness.mozilla.buildbot import TBPL_SUCCESS, TBPL_WARNING, TBPL_FAILURE
from mozharness.mozilla.testing.testbase import TestingMixin, testing_config_options


class MarionetteOutputParser(OutputParser):
    """
    A class that extends OutputParser such that it can parse the number of
    passed/failed/todo tests from the output.
    """

    summary = re.compile(r'(passed|failed|todo): (\d+)')

    def __init__(self, **kwargs):
        self.failed = 0
        self.passed = 0
        self.todo = 0
        super(MarionetteOutputParser, self).__init__(**kwargs)

    def parse_single_line(self, line):
        m = self.summary.match(line)
        if m:
            try:
                setattr(self, m.group(1), int(m.group(2)))
            except ValueError:
                # ignore bad values
                pass
        super(MarionetteOutputParser, self).parse_single_line(line)


class MarionetteTest(TestingMixin, BaseScript):
    config_options = [
        [["--test-type"],
        {"action": "store",
         "dest": "test_type",
         "default": "browser",
         "help": "The type of tests to run",
        }],
        [["--marionette-address"],
        {"action": "store",
         "dest": "marionette_address",
         "default": None,
         "help": "The host:port of the Marionette server running inside Gecko.  Unused for emulator testing",
        }],
        [["--emulator"],
        {"action": "store",
         "type": "choice",
         "choices": ['arm'],
         "dest": "emulator",
         "default": None,
         "help": "Use an emulator for testing",
        }],
        [["--test-manifest"],
        {"action": "store",
         "dest": "test_manifest",
         "default": "unit-tests.ini",
         "help": "Path to test manifest to run relative to the Marionette "
                 "tests directory",
        }]] + copy.deepcopy(testing_config_options)

    error_list = [
        {'substr': 'FAILED (errors=', 'level': ERROR},
    ]

    mozbase_dir = os.path.join('tests', 'mozbase')
    virtualenv_modules = [
        { 'manifestparser': os.path.join(mozbase_dir, 'manifestdestiny') },
        { 'mozhttpd': os.path.join(mozbase_dir, 'mozhttpd') },
        { 'mozinfo': os.path.join(mozbase_dir, 'mozinfo') },
        { 'mozinstall': os.path.join(mozbase_dir, 'mozinstall') },
        { 'mozprofile': os.path.join(mozbase_dir, 'mozprofile') },
        { 'mozprocess': os.path.join(mozbase_dir, 'mozprocess') },
        { 'mozrunner': os.path.join(mozbase_dir, 'mozrunner') },
    ]

    def __init__(self, require_config_file=False):
        super(MarionetteTest, self).__init__(
            config_options=self.config_options,
            all_actions=['clobber',
                         'read-buildbot-config',
                         'download-and-extract',
                         'create-virtualenv',
                         'install',
                         'run-marionette'],
            default_actions=['clobber',
                             'download-and-extract',
                             'create-virtualenv',
                             'install',
                             'run-marionette'],
            require_config_file=require_config_file,
            config={'virtualenv_modules': self.virtualenv_modules,
                    'require_test_zip': True,})

        # these are necessary since self.config is read only
        c = self.config
        self.installer_url = c.get('installer_url')
        self.installer_path = c.get('installer_path')
        self.binary_path = c.get('binary_path')
        self.test_url = self.config.get('test_url')

    def _pre_config_lock(self, rw_config):
        if not self.config.get('emulator') and not self.config.get('marionette_address'):
                self.fatal("You need to specify a --marionette-address for non-emulator tests! (Try --marionette-address localhost:2828 )")

    def query_abs_dirs(self):
        if self.abs_dirs:
            return self.abs_dirs
        abs_dirs = super(MarionetteTest, self).query_abs_dirs()
        dirs = {}
        dirs['abs_test_install_dir'] = os.path.join(
            abs_dirs['abs_work_dir'], 'tests')
        dirs['abs_marionette_dir'] = os.path.join(
            dirs['abs_test_install_dir'], 'marionette', 'marionette')
        dirs['abs_marionette_tests_dir'] = os.path.join(
            dirs['abs_test_install_dir'], 'marionette', 'tests', 'testing',
            'marionette', 'client', 'marionette', 'tests')
        dirs['abs_gecko_dir'] = os.path.join(
            abs_dirs['abs_work_dir'], 'gecko')
        dirs['abs_emulator_dir'] = os.path.join(
            abs_dirs['abs_work_dir'], 'emulator')
        for key in dirs.keys():
            if key not in abs_dirs:
                abs_dirs[key] = dirs[key]
        self.abs_dirs = abs_dirs
        return self.abs_dirs

    def _build_arg(self, option, value):
        """
        Build a command line argument
        """
        if not value:
            return []
        return [str(option), str(value)]

    def download_and_extract(self):
        super(MarionetteTest, self).download_and_extract()
        if self.config.get('emulator'):
            dirs = self.query_abs_dirs()
            self.workdir = dirs['abs_work_dir']
            self.mkdir_p(dirs['abs_emulator_dir'])
            self._download_unzip(self.config['emulator_url'], dirs['abs_emulator_dir'])
            self.mkdir_p(dirs['abs_gecko_dir'])
            tar = self.query_exe('tar', return_type='list')
            self.run_command(tar + ['zxf', self.installer_path],
                             cwd=dirs['abs_gecko_dir'],
                             error_list=TarErrorList,
                             halt_on_failure=True)

    def install(self):
        if self.config.get('emulator'):
            self.info("Emulator tests; skipping.")
        else:
            super(MarionetteTest, self).install()

    def run_marionette(self):
        """
        Run the Marionette tests
        """
        dirs = self.query_abs_dirs()

        error_list = self.error_list
        error_list.extend(PythonErrorList)

        # build the marionette command arguments
        python = self.query_python_path('python')
        cmd = [python, '-u', os.path.join(dirs['abs_marionette_dir'],
                                          'runtests.py')]
        if self.config.get('emulator'):
            cmd.extend(self._build_arg('--emulator', self.config['emulator']))
            cmd.extend(self._build_arg('--gecko-path',
                                       os.path.join(dirs['abs_gecko_dir'], 'b2g')))
            cmd.extend(self._build_arg('--homedir',
                                       os.path.join(dirs['abs_emulator_dir'],
                                                    'b2g-distro')))

        else:
            cmd.extend(self._build_arg('--binary', self.binary_path))
            cmd.extend(self._build_arg('--address', self.config['marionette_address']))
        cmd.extend(self._build_arg('--type', self.config['test_type']))
        manifest = os.path.join(dirs['abs_marionette_tests_dir'],
                                self.config['test_manifest'])
        cmd.append(manifest)

        marionette_parser = MarionetteOutputParser(config=self.config,
                                                   log_obj=self.log_obj,
                                                   error_list=error_list)
        code = self.run_command(cmd,
                                output_parser=marionette_parser)
        level = INFO
        if code == 0:
            status = "success"
            tbpl_status = TBPL_SUCCESS
        elif code == 10:
            status = "test failures"
            tbpl_status = TBPL_WARNING
        else:
            status = "harness failures"
            level = ERROR
            tbpl_status = TBPL_FAILURE

        # generate the TinderboxPrint line for TBPL
        emphasize_fail_text = '<em class="testfail">%s</em>'
        if marionette_parser.passed == 0 and marionette_parser.failed == 0:
            tsummary = emphasize_fail_text % "T-FAIL"
        else:
            failed = "0"
            if marionette_parser.failed > 0:
                failed = emphasize_fail_text % str(marionette_parser.failed)
            tsummary = "%d/%s/%d" % (marionette_parser.passed,
                                     failed,
                                     marionette_parser.todo)
        self.info("TinderboxPrint: marionette<br/>%s\n" % tsummary)

        self.add_summary("Marionette exited with return code %s: %s" % (code,
                                                                        status),
                         level=level)
        self.buildbot_status(tbpl_status)


if __name__ == '__main__':
    marionetteTest = MarionetteTest()
    marionetteTest.run()
