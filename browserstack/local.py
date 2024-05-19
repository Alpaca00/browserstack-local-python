import subprocess
import os
import json
import logging
from typing import Optional
import psutil
from threading import Lock

from browserstack.local_binary import LocalBinary  # noqa
from browserstack.bserrors import BrowserStackLocalError  # noqa

logger = logging.getLogger(__name__)
try:
    from importlib.metadata import (
        version as package_version, # noqa
        PackageNotFoundError,  # noqa
    )
except ImportError:
    import pkg_resources


class LocalSingleton:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.__initialized = False
        return cls._instance

    def __init__(
        self,
        key: Optional[str] = None,
        binary_path: Optional[str] = None,
        **kwargs: any,
    ):
        with self.__class__._lock:
            if not self.__initialized:
                self.key = os.environ.get("BROWSERSTACK_ACCESS_KEY", key)
                self.options = kwargs
                self.local_logfile_path = os.path.join(os.getcwd(), "local.log")
                self.binary_path = binary_path
                self.__initialized = True

    def __xstr(self, key: Optional[str], value: any) -> list[str]:  # noqa
        """Stringify the key-value pair for the command line."""
        if key is None:
            return [""]
        if str(value).lower() == "true":
            return ["-" + key]
        elif str(value).lower() == "false":
            return [""]
        else:
            return ["-" + key, value]

    @staticmethod
    def get_package_version() -> str:  # noqa
        """Gets the version of the BrowserStack Local package.

        :return: The version of the BrowserStack Local package.
        """
        name = "browserstack-local"
        version = "None"  # noqa
        use_fallback = False
        try:
            temp = package_version  # noqa
        except NameError:
            use_fallback = True

        if use_fallback:
            try:
                version = pkg_resources.get_distribution(name).version  # noqa
            except pkg_resources.DistributionNotFound:  # noqa
                version = "None"
        else:
            try:
                version = package_version(name)
            except PackageNotFoundError:
                version = "None"

        return version

    def _generate_cmd(self) -> list[str]:
        """Generates the command to start the BrowserStack Local binary."""
        cmd = [
            self.binary_path,
            "-d",
            "start",
            "-logFile",
            self.local_logfile_path,
            "-k",
            self.key,
            "--source",
            "python:" + self.get_package_version(),
        ]
        for o in self.options.keys():
            if self.options.get(o) is not None:
                cmd = cmd + self.__xstr(o, self.options.get(o))
        return cmd

    def _generate_stop_cmd(self) -> list[str]:
        """Generates the command to stop the BrowserStack Local binary."""
        cmd = self._generate_cmd()
        cmd[2] = "stop"
        return cmd

    def start(self, **kwargs: any) -> None:
        """Starts the BrowserStack Local binary."""
        for k, v in kwargs.items():
            self.options[k] = v

        if "key" in self.options:
            self.key = self.options["key"]
            del self.options["key"]

        if "binarypath" in self.options:  # noqa
            self.binary_path = self.options["binarypath"]  # noqa
            del self.options["binarypath"]  # noqa
        else:
            self.binary_path = LocalBinary().get_binary()

        if "logfile" in self.options:
            self.local_logfile_path = self.options["logfile"]
            del self.options["logfile"]

        if "onlyCommand" in kwargs and kwargs["onlyCommand"]:
            return

        if "source" in self.options:
            del self.options["source"]

        self.proc = subprocess.Popen(  # noqa
            self._generate_cmd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )  # noqa nosec
        out, err = self.proc.communicate()

        os.system('echo "" > "' + self.local_logfile_path + '"')
        try:
            if out:
                output_string = out.decode()
            else:
                output_string = err.decode()

            data = json.loads(output_string)

            if data["state"] != "connected":
                raise BrowserStackLocalError(data["message"]["message"])
            else:
                self.pid = data["pid"]  # noqa
        except ValueError:
            logger.error(
                "BinaryOutputParseError: Raw String = '{}'".format(output_string)  # noqa
            )
            raise BrowserStackLocalError(
                'Error parsing JSON output from daemon. Raw String = "{}"'.format(
                    output_string
                )
            )

    def is_running(self) -> bool:
        """Checks if the BrowserStack Local binary is running.

        :return: True if running, False otherwise.
        """
        return hasattr(self, "pid") and psutil.pid_exists(self.pid)

    def stop(self) -> None:
        """Stops the BrowserStack Local binary."""
        try:
            proc = subprocess.Popen(
                self._generate_stop_cmd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            proc.communicate()
        except Exception as e:
            logger.error(f"Error stopping BrowserStack Local: {e}")

    def __enter__(self) -> "LocalSingleton":
        """Starts the BrowserStack Local binary."""
        self.start(**self.options)
        return self

    def __exit__(self, *args: any) -> None:
        """Stops the BrowserStack Local binary."""
        self.stop()
