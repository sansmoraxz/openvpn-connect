import logging
import os
import random
import subprocess
import time
from enum import IntEnum
import threading


class VPNState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    DISCONNECTING = 3


class OpenVPN(object):
    def __init__(self, path: str = './configs/ovpn_configs/', auth_file: str = 'vpn-auth.txt'):
        self.logger = logging.getLogger(__name__)
        self.path = path
        self._state = VPNState.DISCONNECTED
        self.configs = {
            k: {'bound': False, 'lastUsed': 0} for k in os.listdir(self.path) if k.endswith('.ovpn')
        }
        self.current_config = None
        self._process = None
        self.auth_file = auth_file
        self.logger.info('OpenVPN initialized')

    def __del__(self):
        # cleanup
        if self._state == VPNState.CONNECTED or self._state == VPNState.CONNECTING:
            self.disconnect()

    def get_config(self):
        """Get the config"""
        return self.configs

    def connect(self, config: str):
        """Connect to the config"""
        self.current_config = config
        self._state = VPNState.CONNECTING
        self.logger.info('Connecting using config: %s', config)
        self._process = subprocess.Popen([
            'sudo',
            'openvpn',
            '--config', self.path + config,
            '--auth-user-pass', self.path + self.auth_file
        ], stdout=open('/tmp/openvpn.log', 'w'))
        self.configs[config] = {'bound': True, 'lastUsed': time.time_ns()}

        time.sleep(3)

        # wait for initialization to be done
        self.logger.info('waiting for connection...')
        while self._state == VPNState.CONNECTING:
            if self._process.poll() is not None:
                self.logger.critical('Connection failed')
                self._state = VPNState.DISCONNECTED
                self.configs[config] = {'bound': False, 'lastUsed': time.time_ns()}
                self._process = None
                return
            grep_init_search_p = subprocess.run(
                ['grep', 'Initialization Sequence Completed', '/tmp/openvpn.log'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if grep_init_search_p.returncode == 0:  # success
                self._state = VPNState.CONNECTED
                threading.Thread(target=self.update_state_poll, args=[5]).start()
                self.logger.info('Connected')
                return
            time.sleep(1)

    def disconnect(self):
        """Disconnect the vpn"""
        self.logger.info('Disconnecting...')
        self._state = VPNState.DISCONNECTING
        self._process.terminate()
        self.configs[self.current_config] = {'bound': False, 'lastUsed': time.time_ns()}
        self.current_config = None
        self._state = VPNState.DISCONNECTED
        self._process = None
        self.logger.info('Disconnected')

    def update_state_poll(self, interval):
        if self._process is None:
            return
        if self._state == VPNState.CONNECTED:
            while self._process.poll() is None:
                time.sleep(interval)
            self.logger.critical('Connection issues, disconnecting current vpn %s', self.current_config)
            self.disconnect()

    def connect_random(self):
        if self.configs is None or len(self.configs) == 0:
            print('No configs found')
            return
        self.logger.info('Connecting to random config')
        random_config = random.choice(
            [config for config in self.configs if self.configs[config]['bound'] is False]
        )
        self.connect(random_config)
