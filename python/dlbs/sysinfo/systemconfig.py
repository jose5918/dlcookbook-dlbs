# (c) Copyright [2017] Hewlett Packard Enterprise Development LP
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The SysInfo class that collects various system-level information.

The following parameters affect collection process:
```
-Pexp.sys_info = "inxi,cpuinfo,meminfo,lscpu,nvidiasmi"
```
The value is a comma separated string that defines what tools should be used to
collect information:

1.  `inxi`      The inxi must be available (https://github.com/smxi/inxi). It is
                output of `inxi -Fbfrlp`.
2.  `cpuinfo`   Content of `/proc/cpuinfo`
3.  `meminfo`   Content of `/proc/meminfo`
4.  `lscpu`     Output of `lscpu`
5.  `nvidiasmi` Output of `/usr/bin/nvidia-smi -q`

In addition, a complete output in a json format can be obtained with:
```
python ./python/dlbs/experimenter.py sysinfo
```
"""
from __future__ import print_function
import subprocess
import os
import re
import shlex
import json
import logging
#import functools
from collections import OrderedDict
from dlbs.utils import Modules

if Modules.HAVE_NUMPY:
    import numpy as np
if Modules.HAVE_PANDAS:
    import pandas as pd

class SysInfo(object):

    def __init__(self,
                 specs='inxi,cpuinfo,meminfo,lscpu,nvidiasmi,dmi',
                 namespace='hw',
                 inxi_path=None):
        self.specs = set(specs.split(','))
        self.namespace = namespace
        self.inxi_path = 'inxi' if inxi_path is None else os.path.join(inxi_path, 'inxi')

    def collect(self):
        info = {}
        def _key(name):
            return self.namespace + '.' + name

        if 'inxi' in self.specs:
            info[_key('inxi')] = SysInfo.inxi(self.inxi_path)
        if 'cpuinfo' in self.specs:
            info[_key('cpuinfo')] = SysInfo.cpuinfo()
        if 'meminfo' in self.specs:
            info[_key('meminfo')] = SysInfo.meminfo()
        if 'lscpu' in self.specs:
            info[_key('lscpu')] = SysInfo.lscpu()
        if 'nvidiasmi' in self.specs:
            info[_key('nvidiasmi')] = SysInfo.nvidiasmi() if Modules.HAVE_NUMPY and Modules.HAVE_PANDAS  else {}
        if 'dmi' in self.specs:
            info[_key('dmi')] = SysInfo.dmi()

        return info

    @staticmethod
    def dmi():
        """Get various info from /sys/devices/virtual/dmi/id that does not require SUDO.

        DMI - Desktop Management Interface: https://linux.die.net/man/8/dmidecode
        https://askubuntu.com/questions/179958/how-do-i-find-out-my-motherboard-model/179964
        """
        base_path = '/sys/devices/virtual/dmi/id/'
        # Files that we most likely can read without SUDO rights and that can be useful.
        # Most likely, in that folder there are other files that we can read but it may
        # not be the good idea to expose that kind of info (like BIOS info etc).
        # 'bios_date', 'bios_vendor', 'bios_version'
        dmi_files = [
            'board_name',      # ProLiant XL250a Gen9
            'board_vendor',    # HP
            'product_name',    # ProLiant XL250a Gen9
            'sys_vendor'       # HP
        ]
        info = {}
        for dmi_file in dmi_files:
            file_name = base_path + dmi_file
            if not os.path.exists(file_name):
                continue
            try:
                with open(file_name, "r") as file_obj:
                    dmi_value = file_obj.read().strip()
                info[dmi_file] = dmi_value
            except IOError:
                pass
        return info

    @staticmethod
    def inxi(inxi_exe=None):
        """Descriptions ...
        """
        try:
            process = subprocess.Popen(shlex.split("{} -Fbfrlp".format(inxi_exe)),
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds=True)
            output = process.communicate()[0][3:]
        except OSError:
            return None

        output_lines = re.split(r'\n', re.sub(r'\\x03', '', re.sub(r"\\x0312", "", output)))[2:-1]
        info = OrderedDict()
        for _, line in enumerate(output_lines):
            if line[0] != ' ': # key
                try:
                    key, prop = line.split(":")
                    info[key] = [prop.strip()]
                except ValueError as err:
                    logging.warn("INXI output parsing error on line: " + line)
                    logging.exception(err)
        return info

    @staticmethod
    def cpuinfo():
        """Description ...
        """
        recs = []
        try:
            with open('/proc/cpuinfo', 'r') as fhandle:
                lines = [re.sub(r'\t', '', l.strip()) for l in fhandle.readlines()]
        except IOError:
            return None

        for line in lines:
            if len(line) == 0:
                continue
            key_val = line.split(':')
            key = key_val[0]
            try:
                val = key_val[1].strip()
            except Exception as err:
                print(line)
                print(err)
                raise err
            if key == 'processor':
                odd = OrderedDict()
                recs.append(odd)
            odd[key] = val
        return recs

    @staticmethod
    def meminfo():
        """Description...
        """
        try:
            with open('/proc/meminfo', 'r') as fhandle:
                info = OrderedDict([
                    (x[0], x[1].strip())
                    for x in [
                        re.sub(r'\t', '', l.strip()).split(':') for l in
                        fhandle.readlines() if len(l.strip()) > 0
                    ]
                ])
        except IOError:
            return None

        return info

    @staticmethod
    def lscpu():
        """Description...
        """
        try:
            process = subprocess.Popen(shlex.split("lscpu"),
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds=True)
            output = str(process.communicate()[0]).split('\n')
        except OSError:
            return None

        info = OrderedDict([
            (x[0], x[1].strip())
            for x in [
                re.sub(r'\t', '', l.strip()).split(':') for l in output if len(l.strip()) > 0
            ]
        ])
        return info

    @staticmethod
    def nvidiasmi():
        """Description ...
        """
        try:
            process = subprocess.Popen(shlex.split("/usr/bin/nvidia-smi -q"),
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds=True)
            output = process.communicate()[0][3:]
        except OSError:
            return None

        output_lines = re.split(r'\n', re.sub(r'\\x03', '', re.sub(r"\\x0312", "", output)))[2:-1]
        lines = [line for line in output_lines if len(line.strip()) > 0]

        lines = lines[3:]
        recs = []
        maxlevel = 0
        for l in lines:
            l = l.rstrip()
            m = l.strip()
            level = int((len(l)-len(m))/4)
            maxlevel = max(level, maxlevel)
            key_val = re.split(' : ', m)
            key = key_val[0].strip()
            if len(key_val) == 2:
                val = key_val[1].strip()
            else:
                val = ''
            recs.append((level, key, val))
        row = [None]*(maxlevel+2)
        rows = []
        values = []
        for rec in recs:
            (level, key, val) = rec
            row[level] = key
            for i in range(level+1, len(row)):
                row[i] = None
            rows.append(list(row))
            values.append(val)
        data_frame = pd.DataFrame(rows)
        data_frame = data_frame.replace(np.nan, '', regex=True)
        data_frame[data_frame.columns.values] = data_frame[data_frame.columns.values].astype(str)
        gpus = OrderedDict()
        for row, value in zip(data_frame.iterrows(), values):
            if value == '':
                continue
            row = row[1].values
            if row[0] not in gpus:
                gpus[row[0]] = OrderedDict()
            key = '/'.join([str(f) for f in row[1:] if f != ''])
            gpus[row[0]][key] = value
        return gpus

#def nvidatopo(jsonfile):
#    """Description ...
#    """
#    process = subprocess.Popen(shlex.split("/usr/bin/nvidia-smi -q"),
#                               stdin=subprocess.PIPE,
#                               stdout=subprocess.PIPE,
#                               close_fds=True)
#    output = process.communicate()[0][3:]
#
#    output_lines = re.split(r'\n', re.sub(r'\\x03', '', re.sub(r"\\x0312", "", output)))[2:-1]
#    lines = [line for line in output_lines if len(line.strip()) > 0]
#    with open(jsonfile, 'w') as fhandle:
#        json.dump({'gpu/nvidia-smi/topo': lines}, fhandle, indent=4)
#    return
#
#def sysconfig2json(jfile, inxi_exe=None):
#    """Description...
#    """
#    inxifunc = functools.partial(inxi, inxi_exe)
#    info = OrderedDict([(func()) for func in [cpuinfo, lscpu, meminfo, inxifunc, nvidasmiq]])
#    with open(jfile, 'w') as fhandle:
#        json.dump(info, fhandle, indent=4)


if __name__ == "__main__":
    info = SysInfo().collect()
    print(json.dumps(info, indent=2))
