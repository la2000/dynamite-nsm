import os
import sys
import json
import time
import signal
import shutil
import tarfile
import subprocess
from multiprocessing import Process
from lib import zeek
from lib import const
from lib import utilities

INSTALL_DIRECTORY = '/opt/dynamite/filebeat/'


class FileBeatConfigurator:

    def __init__(self, install_directory=INSTALL_DIRECTORY):
        self.install_directory = install_directory
        self.agent_tag = None
        self.logstash_targets = None
        self.monitor_target_paths = None
        self._parse_filebeatyaml()

    def _parse_filebeatyaml(self):
        for line in open(os.path.join(self.install_directory, 'filebeat.yml')).readlines():
            if not line.startswith('#') and ':' in line:
                if line.strip().startswith('"originating_agent_tag"'):
                    self.agent_tag = line.split(':')[1].strip()[1:-1]
                elif 'hosts:' in line:
                    self.logstash_targets = list(json.loads(line.replace('hosts:', '').strip()))
                elif 'paths:' in line:
                    self.monitor_target_paths = list(json.loads(line.replace('paths:', '')))

    def set_agent_tag(self, agent_tag):
        """
        Create a tag to associate events/entities with the originating agent

        :param agent_tag: A tag associated with the agent
        """
        self.agent_tag = agent_tag

    def set_logstash_targets(self, target_hosts):
        """
        Define where events should be sent

        :param target_hosts: A list of Logstash hosts, and their service port (E.G ["192.168.0.9:5044"]
        """
        self.logstash_targets = target_hosts

    def set_monitor_target_paths(self, monitor_log_paths):
        """
        Define which logs to monitor and send to Logstash hosts

        :param monitor_log_paths: A list of log files to monitor (wild card '*' accepted)
        """
        self.monitor_target_paths = monitor_log_paths

    def get_agent_tag(self):
        return self.agent_tag

    def get_logstash_targets(self):
        return self.logstash_targets

    def get_monitor_target_paths(self):
        return self.monitor_target_paths

    def write_config(self):
        config_output = ''
        for line in open(os.path.join(self.install_directory, 'filebeat.yml')).readlines():
            if not line.startswith('#') and ':' in line:
                if 'originating_agent_tag' in line:
                    line = '   fields: ["originating_agent_tag": "{}"]\n'.format(self.agent_tag)
                elif 'hosts:' in line:
                    line = '   hosts: {}\n'.format(json.dumps(self.logstash_targets))
                elif 'paths:' in line:
                    line = '  paths: {}\n'.format(json.dumps(self.monitor_target_paths))
            config_output += line
        with open(os.path.join(self.install_directory, 'filebeat.yml'), 'w') as out_config:
            out_config.write(config_output)


class FileBeatInstaller:

    def __init__(self, monitor_paths=(zeek.INSTALL_DIRECTORY + 'logs/current/*.log'),
                 install_directory=INSTALL_DIRECTORY):
        self.monitor_paths = list(monitor_paths)
        self.install_directory = install_directory

    @staticmethod
    def download_filebeat(stdout=False):
        """
        Download Filebeat archive

        :param stdout: Print output to console
        """
        for url in open(const.FILE_BEAT_MIRRORS, 'r').readlines():
            if utilities.download_file(url, const.FILE_BEAT_ARCHIVE_NAME, stdout=stdout):
                break

    @staticmethod
    def extract_filebeat(stdout=False):
        """
        Extract Filebeat to local install_cache

        :param stdout: Print output to console
        """
        if stdout:
            sys.stdout.write('[+] Extracting: {} \n'.format(const.FILE_BEAT_ARCHIVE_NAME))
        try:
            tf = tarfile.open(os.path.join(const.INSTALL_CACHE, const.FILE_BEAT_ARCHIVE_NAME))
            tf.extractall(path=const.INSTALL_CACHE)
            if stdout:
                sys.stdout.write('[+] Complete!\n')
                sys.stdout.flush()
        except IOError as e:
            sys.stderr.write('[-] An error occurred while attempting to extract file. [{}]\n'.format(e))

    def setup_filebeat(self, stdout=False):
        if stdout:
            sys.stdout.write('[+] Creating Filebeat install directory.\n')
        subprocess.call('mkdir -p {}'.format(self.install_directory), shell=True)
        utilities.copytree(os.path.join(const.INSTALL_CACHE, const.FILE_BEAT_DIRECTORY_NAME), self.install_directory)
        shutil.copy(os.path.join(const.DEFAULT_CONFIGS, 'filebeat', 'filebeat.yml'),
                    self.install_directory)
        beats_config = FileBeatConfigurator(self.install_directory)
        beats_config.set_logstash_targets(self.monitor_paths)


class FileBeatProcess:

    def __init__(self, install_directory=INSTALL_DIRECTORY):
        self.install_directory = install_directory
        self.config = FileBeatConfigurator(self.install_directory)

        if not os.path.exists('/var/run/dynamite/filebeat/'):
            subprocess.call('mkdir -p {}'.format('/var/run/dynamite/filebeat/'), shell=True)

        try:
            self.pid = int(open('/var/run/dynamite/filebeat/filebeat.pid').read())
        except (IOError, ValueError):
            self.pid = -1

    def start(self, stdout=False):
        """
        Start the Filebeat daemon
        :param stdout: Print output to console
        :return: True if started successfully
        """
        def start_shell_out():
            command = '{}/filebeat -C {}/filebeat.yml & echo $! > /var/run/dynamite/filebeat/filebeat.pid"'.format(
                self.config.install_directory, self.config.install_directory)
            subprocess.call(command, shell=True)

        if stdout:
            sys.stdout.write('[+] Starting Filebeat\n')
        time.sleep(2)
        if not utilities.check_pid(self.pid):
            Process(target=start_shell_out).start()
        else:
            sys.stderr.write('[-] Filebeat is already running on PID [{}]\n'.format(self.pid))
            return True

    def stop(self, stdout=False):
        """
        Stop the LogStash process

        :param stdout: Print output to console
        :return: True if stopped successfully
        """
        alive = True
        attempts = 0
        while alive:
            try:
                if stdout:
                    sys.stdout.write('[+] Attempting to stop Filebeat [{}]\n'.format(self.pid))
                if attempts > 3:
                    sig_command = signal.SIGINT
                else:
                    sig_command = signal.SIGTERM
                attempts += 1
                os.kill(self.pid, sig_command)
                time.sleep(1)
                alive = utilities.check_pid(self.pid)
            except Exception as e:
                sys.stderr.write('[-] An error occurred while attempting to stop Filebeat: {}\n'.format(e))
                return False
        return True


