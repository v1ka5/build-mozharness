#!/usr/bin/env python
"""maemo_multi_locale_build.py

Override MultiLocaleBuild with Maemo- and scratchbox-isms.
"""

import hashlib
import os
import re
import sys

sys.path.insert(1, os.path.dirname(sys.path[0]))

from mozharness.base.errors import MakefileErrorList, PythonErrorList
from mozharness.l10n.multi_locale_build import MultiLocaleBuild



# MaemoMultiLocaleBuild {{{1
class MaemoMultiLocaleBuild(MultiLocaleBuild):
    config_options = MultiLocaleBuild.config_options + [[
     ["--deb-name",],
     {"action": "store",
      "dest": "deb_name",
      "type": "string",
      "help": "Specify the name of the deb",
     }
    ],[
     ["--sbox-target",],
     {"action": "store",
      "dest": "sbox_target",
      "type": "choice",
      "choices": ["FREMANTLE_ARMEL", "CHINOOK-ARMEL-2007"],
      "default": "FREMANTLE_ARMEL",
      "help": "Specify the scratchbox target"
     }
    ],[
     ["--sbox-home",],
     {"action": "store",
      "dest": "sbox_home",
      "type": "string",
      "default": "/scratchbox/users/cltbld/home/cltbld/",
      "help": "Specify the scratchbox user home directory"
     }
    ],[
     ["--sbox-root",],     {"action": "store",
      "dest": "sbox_root",
      "type": "string",
      "default": "/scratchbox/users/cltbld",      "help": "Specify the scratchbox user home directory"
     }
    ],[
     ["--sbox_path",],
     {"action": "store",
      "dest": "sbox_path",
      "type": "string",
      "default": "/scratchbox/moz_scratchbox",
      "help": "Specify the scratchbox executable"
     }
    ]]

    def __init__(self, require_config_file=True):
        super(MaemoMultiLocaleBuild, self).__init__(require_config_file=require_config_file)

    def build(self):
        if 'build' not in self.actions:
            self.action_message("Skipping build step.")
            return
        self.action_message("Building.")
        c = self.config
        dirs = self.query_abs_dirs()
        self.copyfile(os.path.join(dirs['abs_work_dir'], c['mozconfig']),
                      os.path.join(dirs['abs_mozilla_dir'], 'mozconfig'),
                      error_level='fatal')
        command = "make -f client.mk build"
        # TODO a better way to do envs
        env = self.generate_env(partial_env=c['java_env'],
                                replace_dict={'PATH': os.environ['PATH']})
        self.run_command(command, cwd=dirs['abs_mozilla_dir'], env=env,
                         error_list=MakefileErrorList,
                         halt_on_failure=True)

    def add_locales(self):
        if 'add-locales' not in self.actions:
            self.action_message("Skipping add-locales step.")
            return
        self.action_message("Adding locales to the apk.")
        c = self.config
        dirs = self.query_abs_dirs()
        locales = self.query_locales()

        for locale in locales:
            self.run_compare_locales(locale, halt_on_failure=True)
            command = 'make chrome-%s L10NBASEDIR=%s' % (locale, dirs['abs_l10n_dir'])
            if c['merge_locales']:
                command += " LOCALE_MERGEDIR=%s" % dirs['abs_merge_dir']
                self.run_command(command, cwd=dirs['abs_locales_dir'],
                                 error_list=MakefileErrorList,
                                 halt_on_failure=True)

    def package(self, package_type='en-US'):
        if 'package-%s' % package_type not in self.actions:
            self.action_message("Skipping package-%s." % package_type)
            return
        self.action_message("Packaging %s." % package_type)
        c = self.config
        dirs = self.query_abs_dirs()

        command = "make package"
        # only a little ugly?
        # TODO c['package_env'] that automatically replaces %(PATH),
        # %(abs_work_dir)
        partial_env = c['java_env'].copy()
        env = self.generate_env(partial_env=c['java_env'],
                                replace_dict={'PATH': os.environ['PATH']})
        if package_type == 'multi':
            command += " AB_CD=multi"
            partial_env['MOZ_CHROME_MULTILOCALE'] = "en-US " + \
                                                   ' '.join(self.query_locales())
            self.info("MOZ_CHROME_MULTILOCALE is %s" % partial_env['MOZ_CHROME_MULTILOCALE'])
        if 'jarsigner' in c:
            # hm, this is pretty mozpass.py specific
            partial_env['JARSIGNER'] = os.path.join(dirs['abs_work_dir'],
                                                    c['jarsigner'])
        status = self.run_command(command, cwd=dirs['abs_objdir'], env=env,
                                  error_list=MakefileErrorList,
                                  halt_on_failure=True)
        command = "make package-tests"
        if package_type == 'multi':
            command += " AB_CD=multi"
        status = self.run_command(command, cwd=dirs['abs_objdir'], env=env,
                                  error_list=MakefileErrorList,
                                  halt_on_failure=True)

    def _processCommand(self, **kwargs):
        c = self.config
        command = '%s ' % c['sbox_path']
        if 'return_type' not in kwargs or kwargs['return_type'] != 'output':
            command += '-p '
        if 'cwd' in kwargs:
            command += '-d %s ' % kwargs['cwd'].replace(c['sbox_home'], '')
            del kwargs['cwd']
        kwargs['command'] = '%s "%s"' % (command, kwargs['command'].replace(c['sbox_root'], ''))
        if 'return_type' not in kwargs or kwargs['return_type'] != 'output':
            if 'error_list' in kwargs:
                kwargs['error_list'] = PythonErrorList + kwargs['error_list']
            else:
                kwargs['error_list'] = PythonErrorList
            return self.run_command(**kwargs)
        else:
            del(kwargs['return_type'])
            return self.get_output_from_command(**kwargs)

# __main__ {{{1
if __name__ == '__main__':
    maemo_multi_locale_build = MaemoMultiLocaleBuild()
    maemo_multi_locale_build.run()