import os
import sys
from dynamite_nsm import const
from dynamite_nsm.components.base import execution_strategy
from dynamite_nsm.services.zeek import install as zeek_install
from dynamite_nsm.services.zeek import process as zeek_process
from dynamite_nsm.services.zeek import profile as zeek_profile
from dynamite_nsm.services.filebeat import install as filebeat_install
from dynamite_nsm.services.filebeat import process as filebeat_process
from dynamite_nsm.services.filebeat import profile as filebeat_profile
from dynamite_nsm.services.suricata import install as suricata_install
from dynamite_nsm.services.suricata import process as suricata_process
from dynamite_nsm.services.suricata import profile as suricata_profile

from dynamite_nsm.utilities import prompt_input


def check_agent_deps_installed():
    try:
        with open(os.path.join(const.CONFIG_PATH, '.agent_environment_prepared'), 'r'):
            return
    except IOError:
        print("[-] Agent dependencies were not installed. Install with 'dynamite agent-dependencies install'")
        exit(0)


def get_agent_status():
    zeek_profiler = zeek_profile.ProcessProfiler()
    suricata_profiler = suricata_profile.ProcessProfiler()
    filebeat_profiler = filebeat_profile.ProcessProfiler()

    agent_status = {}
    if zeek_profiler.is_installed:
        agent_status.update({
            'zeek': zeek_process.ProcessManager().status()
        })
    if suricata_profiler.is_installed:
        agent_status.update({
            'suricata': suricata_process.ProcessManager().status()
        })
    if filebeat_profiler.is_installed:
        agent_status.update({
            'filebeat': filebeat_process.ProcessManager().status()
        })
    return agent_status


def get_installed_agent_analyzers():
    zeek_profiler = zeek_profile.ProcessProfiler()
    suricata_profiler = suricata_profile.ProcessProfiler()
    filebeat_profiler = filebeat_profile.ProcessProfiler()

    agent_analyzers = []
    if zeek_profiler.is_installed:
        agent_analyzers.append('Zeek')
    if suricata_profiler.is_installed:
        agent_analyzers.append('Suricata')
    if filebeat_profiler.is_installed:
        agent_analyzers.append('Filebeat')
    return agent_analyzers


def print_message(msg):
    print(msg)


def remove_filebeat_tar_archive():
    dir_path = os.path.join(const.INSTALL_CACHE, const.FILE_BEAT_ARCHIVE_NAME)
    if os.path.exists(dir_path):
        os.remove(dir_path)


def remove_zeek_tar_archive():
    dir_path = os.path.join(const.INSTALL_CACHE, const.ZEEK_ARCHIVE_NAME)
    if os.path.exists(dir_path):
        os.remove(dir_path)


def remove_suricata_tar_archive():
    dir_path = os.path.join(const.INSTALL_CACHE, const.SURICATA_ARCHIVE_NAME)
    if os.path.exists(dir_path):
        os.remove(dir_path)


def prompt_agent_uninstall(prompt_user=True, stdout=True):
    if prompt_user:
        sys.stderr.write(
            '[-] WARNING! Removing Monitor Will Remove the Agent and all of it\'s installed components: {}.\n'.format(
                get_installed_agent_analyzers()))
        resp = prompt_input('Are you sure you wish to continue? ([no]|yes): ')
        while resp not in ['', 'no', 'yes']:
            resp = prompt_input('Are you sure you wish to continue? ([no]|yes): ')
        if resp != 'yes':
            if stdout:
                sys.stdout.write('[+] Exiting\n')
            exit(0)


class AgentInstallStrategy(execution_strategy.BaseExecStrategy):

    def __init__(self, capture_network_interfaces, logstash_targets, agent_analyzers=('zeek', 'suricata'),
                 tag=None, stdout=True, verbose=False):
        execution_strategy.BaseExecStrategy.__init__(
            self,
            strategy_name="agent_install",
            strategy_description="Install Zeek and/or Suricata along with Filebeat.",
        )
        self.add_function(func=check_agent_deps_installed, argument_dict={})
        if not filebeat_profile.ProcessProfiler().is_installed:
            filebeat_args = {
                'logstash_targets': list(logstash_targets),
                'agent_tag': str(tag),
                'install_directory': '/opt/dynamite/filebeat/',
                'download_filebeat_archive': True,
                'stdout': bool(stdout)
            }
            monitor_log_paths = []
            if 'zeek' in agent_analyzers:
                monitor_log_paths.append("/opt/dynamite/zeek/logs/current/*.log")
            if 'suricata' in agent_analyzers:
                monitor_log_paths.append('/var/log/dynamite/suricata/eve.json')
            filebeat_args.update({
                'monitor_log_paths': monitor_log_paths
            })
            self.add_function(func=filebeat_install.install_filebeat, argument_dict=filebeat_args)
        else:
            self.add_function(func=print_message,
                              argument_dict={"msg": 'Skipping Filebeat installation; already installed'},
                              return_format=None)
        if not zeek_profile.ProcessProfiler().is_installed and 'zeek' in agent_analyzers:
            self.add_function(func=zeek_install.install_zeek, argument_dict={
                'configuration_directory': '/etc/dynamite/zeek/',
                'install_directory': '/opt/dynamite/zeek',
                'capture_network_interfaces': list(capture_network_interfaces),
                'download_zeek_archive': True,
                'stdout': bool(stdout),
                'verbose': bool(verbose)
            })
        else:
            self.add_function(func=print_message, argument_dict={"msg": 'Skipping Zeek installation.'},
                              return_format=None)
        if not suricata_profile.ProcessProfiler().is_installed and 'suricata' in agent_analyzers:
            self.add_function(func=suricata_install.install_suricata, argument_dict={
                'configuration_directory': '/etc/dynamite/suricata/',
                'install_directory': '/opt/dynamite/suricata',
                'log_directory': '/var/log/dynamite/suricata/',
                'capture_network_interfaces': list(capture_network_interfaces),
                'download_suricata_archive': True,
                'stdout': bool(stdout),
                'verbose': bool(verbose)
            })
        else:
            self.add_function(func=print_message, argument_dict={"msg": 'Skipping Suricata installation.'},
                              return_format=None)
        self.add_function(func=print_message, argument_dict={
            "msg": '[+] *** Agent installed successfully. ***\n'
        })
        self.add_function(func=print_message, argument_dict={
            "msg": '[+] Next, Start your agent: '
                   '\'dynamite agent start\'.'
        }, return_format=None)


class AgentUninstallStrategy(execution_strategy.BaseExecStrategy):

    def __init__(self, stdout, prompt_user):
        execution_strategy.BaseExecStrategy.__init__(
            self, strategy_name="agent_uninstall",
            strategy_description="Uninstall Agent.",
            functions=(
                prompt_agent_uninstall,
            ),
            arguments=(
                # prompt_user
                {
                    "prompt_user": bool(prompt_user),
                    "stdout": bool(stdout)
                },
            ),
            return_formats=(
                None,
            )
        )

        self.add_function(func=filebeat_install.uninstall_filebeat, argument_dict={
            'prompt_user': False,
            'stdout': bool(stdout)
        })
        if zeek_profile.ProcessProfiler().is_installed:
            self.add_function(func=zeek_install.uninstall_zeek, argument_dict={
                'prompt_user': False,
                'stdout': bool(stdout)
            })
        if suricata_profile.ProcessProfiler().is_installed:
            self.add_function(func=suricata_install.uninstall_suricata, argument_dict={
                'prompt_user': False,
                'stdout': bool(stdout)
            })

        self.add_function(func=print_message, argument_dict={
            "msg": '[+] *** Agent uninstalled successfully. ***\n'
        })


class AgentProcessStartStrategy(execution_strategy.BaseExecStrategy):

    def __init__(self, stdout, status):
        execution_strategy.BaseExecStrategy.__init__(
            self,
            strategy_name="agent_start",
            strategy_description="Start Agent processes.",
            functions=(
                filebeat_process.start,
            ),
            arguments=(
                # filebeat_process.start
                {
                    "stdout": stdout
                },
            ),
            return_formats=(
                None,
            )

        )
        if zeek_profile.ProcessProfiler().is_installed:
            self.add_function(func=zeek_process.start, argument_dict={
                'stdout': bool(stdout)
            })
        if suricata_profile.ProcessProfiler().is_installed:
            self.add_function(func=suricata_process.start, argument_dict={
                'stdout': bool(stdout)
            })
        if status:
            self.add_function(get_agent_status, {}, return_format="json")


class AgentProcessStopStrategy(execution_strategy.BaseExecStrategy):

    def __init__(self, stdout, status):
        execution_strategy.BaseExecStrategy.__init__(
            self,
            strategy_name="agent_stop",
            strategy_description="Stop Agent processes.",
            functions=(
                filebeat_process.stop,
            ),
            arguments=(
                # filebeat_process.stop
                {
                    "stdout": stdout
                },
            ),
            return_formats=(
                None,
            )

        )
        if zeek_profile.ProcessProfiler().is_installed:
            self.add_function(func=zeek_process.stop, argument_dict={
                'stdout': bool(stdout)
            })
        if suricata_profile.ProcessProfiler().is_installed:
            self.add_function(func=suricata_process.stop, argument_dict={
                'stdout': bool(stdout)
            })
        if status:
            self.add_function(get_agent_status, {}, return_format="json")


class AgentProcessRestartStrategy(execution_strategy.BaseExecStrategy):

    def __init__(self, stdout, status):
        execution_strategy.BaseExecStrategy.__init__(
            self,
            strategy_name="agent_restart",
            strategy_description="Restart Agent processes."
        )
        self.add_function(func=filebeat_process.stop, argument_dict={
            'stdout': bool(stdout)
        })
        self.add_function(func=filebeat_process.start, argument_dict={
            'stdout': bool(stdout)
        })
        if zeek_profile.ProcessProfiler().is_installed:
            self.add_function(func=zeek_process.stop, argument_dict={
                'stdout': bool(stdout)
            })
            self.add_function(func=zeek_process.start, argument_dict={
                'stdout': bool(stdout)
            })
        if suricata_profile.ProcessProfiler().is_installed:
            self.add_function(func=suricata_process.stop, argument_dict={
                'stdout': bool(stdout)
            })
            self.add_function(func=suricata_process.start, argument_dict={
                'stdout': bool(stdout)
            })
        if status:
            self.add_function(get_agent_status, {}, return_format="json")


class AgentProcessStatusStrategy(execution_strategy.BaseExecStrategy):

    def __init__(self):
        execution_strategy.BaseExecStrategy.__init__(
            self, strategy_name="agent_status",
            strategy_description="Get the status of the Agent processes.",
            functions=(
                get_agent_status,
            ),
            arguments=(
                {},
            ),
            return_formats=(
                'json',
            )
        )


# Test Functions


def run_install_strategy():
    agt_install_strategy = AgentInstallStrategy(
        capture_network_interfaces=['eth0'],
        logstash_targets=['localhost:5044'],
        agent_analyzers=('zeek', 'suricata'),
        stdout=True,
        verbose=True
    )
    agt_install_strategy.execute_strategy()


def run_uninstall_strategy():
    agt_uninstall_strategy = AgentUninstallStrategy(
        stdout=True,
        prompt_user=False
    )
    agt_uninstall_strategy.execute_strategy()


def run_process_start_strategy():
    agt_start_strategy = AgentProcessStartStrategy(
        stdout=True,
        status=True
    )
    agt_start_strategy.execute_strategy()


def run_process_stop_strategy():
    agt_stop_strategy = AgentProcessStopStrategy(
        stdout=True,
        status=True
    )
    agt_stop_strategy.execute_strategy()


def run_process_restart_strategy():
    agt_restart_strategy = AgentProcessRestartStrategy(
        stdout=True,
        status=True
    )
    agt_restart_strategy.execute_strategy()


def run_process_status_strategy():
    agt_status_strategy = AgentProcessStatusStrategy()
    agt_status_strategy.execute_strategy()


if __name__ == '__main__':
    run_install_strategy()
    run_process_start_strategy()
    run_process_stop_strategy()
    run_process_restart_strategy()
    run_process_status_strategy()
    run_uninstall_strategy()
    pass
