import hashlib
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict


def calculate_checksum(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def compare_checksums(root_dir):
    file_checksums = defaultdict(dict)

    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            checksum = calculate_checksum(file_path)
            file_checksums[filename][file_path] = checksum

    for filename, paths_checksums in file_checksums.items():
        if len(paths_checksums) > 1:
            checksums = set(paths_checksums.values())
            if len(checksums) != 1:
                print("\n\nFiles have different checksums:")
    else:
        print("\n\nAll YANG models have identical checksums.")


"""
This script connects to a device using SSH and the NETCONF subsystem. It then
requests the YANG schema for each module on the device and writes the schema to
a file in the specified output directory.
"""


class SSHClient:
    """
    A simple SSH client that connects to a device using SSH and the NETCONF
    subsystem. It sends NETCONF messages to the device and reads the responses.
    """

    def __init__(self, host, user, subsystem="", debug=False):
        """Initialize the SSH client."""
        self.host = host
        self.user = user
        self.subsystem = subsystem
        self.client = None
        self.__connected = False
        self.__debug = debug

        self.netconf_hello = """
<?xml version="1.0" encoding="UTF-8"?>
<nc:hello xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
    <nc:capabilities>
        <nc:capability>urn:ietf:params:netconf:base:1.0</nc:capability>
        <nc:capability>urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring</nc:capability>
    </nc:capabilities>
</nc:hello>"""

        self.netconf_state = """
<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="0">
  <get>
    <filter type="subtree">
      <netconf-state xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring">
        <schemas/>
      </netconf-state>
    </filter>
  </get>
</rpc>
]]>]]>"""

        self.netconf_get_schema = """
<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="104">
  <get-schema xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring">
    <identifier>{{IDENTIFIER}}</identifier>
    <version>{{VERSION}}</version>
    <format>yang</format>
  </get-schema>
</rpc>
]]>]]>"""

    def connect(self):
        """
        Create a SSH client and connect to the device using the specified
        username and hostname.
        """
        cmd_args = ["ssh", f"{self.user}@{self.host}"]

        if self.subsystem:
            cmd_args.append("-s")
            cmd_args.append(self.subsystem)

        self.__debug_print(f"Connection string: " + " ".join(cmd_args))

        try:
            self.client = subprocess.Popen(
                cmd_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1024,
                universal_newlines=True,
            )

            if self.client.poll() is not None:
                self.__debug_print("Error connecting to device")
                sys.exit(1)
        except Exception as e:
            self.__debug_print(f"Error connecting to {self.host}: {e}")
            sys.exit(1)

        self.__connected = True

    def __debug_print(self, message):
        """
        Print a debug message if the debug flag is set.
        """

        if self.__debug:
            print(message)

    def __is_connected(self):
        """
        Check if the SSH client is connected to the device.
        """

        if not self.__connected:
            self.__debug_print("Not connected to device")
            sys.exit(1)

    def read_hello(self):
        """
        Read the hello message from the device. The hello message is sent by
        the device when the NETCONF session is established.

        Figure out if we should read line by line or character by charater.
        """

        self.__is_connected()

        data = ""

        self.__debug_print("Reading hello message")

        while not self.client.poll():
            c = self.client.stdout.read(1)
            data += c

            if "]]>]]>" in data:
                break

        data = data.replace("]]>]]>", "")

        self.__debug_print("Received hello message:")
        self.__debug_print(data.encode("utf-8"))
        self.__debug_print("End of hello message")

        if "ietf-netconf-monitoring" not in data:
            print("NETCONF monitoring not supported")
            sys.exit(1)

        if "\n" in data:
            self.__newline_data = True
        else:
            self.__newline_data = False

        return data

    def read_command_output(self):
        """
        Read the output until we hit the "]]>]]>" delimiter. This delimiter is
        used by NETCONF to separate the XML data from the NETCONF framing.
        """

        self.__is_connected()

        data = ""

        self.__debug_print("Reading data")

        if self.__newline_data:
            for line in self.client.stdout:
                data += line
                if "]]>]]>" in line:
                    break
        else:
            while not self.client.poll():
                data += self.client.stdout.read(1)

                if "]]>]]>" in data:
                    break

        data = data.replace("]]>]]>", "")

        self.__debug_print("Received data:")
        self.__debug_print(data.encode("utf-8"))
        self.__debug_print("End of data")

        return data

    def write_command(self, command):
        """
        Write a command to the SSH client. The command should be a string
        containing a valid XML NETCONF message.
        """

        self.__is_connected()

        self.__debug_print("Sending command:")
        self.__debug_print(command)
        self.__debug_print("End of command")

        self.client.stdin.write(command + "\n")
        self.client.stdin.flush()

    def parse_netconf_state(self, data):
        """ "
        Parse the NETCONF state data and return a list of tuples containing the
        module identifier, version, and format.
        """

        root = ET.fromstring(data)
        schemas = []

        for schema in root.iter(
            "{urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring}schema"
        ):
            identifier = schema.find(
                "{urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring}identifier"
            ).text

            version = schema.find(
                "{urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring}version"
            ).text

            yangformat = schema.find(
                "{urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring}format"
            ).text

            if yangformat != "yang":
                self.__debug_print(f"Skipping {identifier}@{version} ({yangformat})")
                continue

            schemas.append((identifier, version))

        return schemas

    def get_netconf_schema(self, identifier, version):
        """
        Get the YANG schema for the specified module identifier and version.
        """

        command = self.netconf_get_schema.replace("{{IDENTIFIER}}", identifier)
        command = command.replace("{{VERSION}}", version)

        self.write_command(command)

        data = self.read_command_output()

        return data

    def parse_netconf_schema_yang(self, data, identifier, version, output_path):
        """
        Parse the NETCONF schema data and write the YANG schema to a file in
        the specified output directory.
        """

        root = ET.fromstring(data)

        data = root.find(
            "{urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring}data"
        ).text

        output_path = f"{output_path}/{identifier}@{version}.yang"
        output_len = len(data)

        self.__debug_print(f"Writing to {output_path} ({output_len} bytes)")

        with open(output_path, "w") as f:
            f.write(data.strip())

        return output_len


def main():
    if len(sys.argv) < 4:
        print("Usage: get_yang.py <hosts> <user> <output_path> (<debug>)")
        sys.exit(1)

    hosts = sys.argv[1]
    user = sys.argv[2]
    output_path = sys.argv[3]

    debug = False
    if len(sys.argv) == 5:
        debug = True

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    for host in hosts.split(","):
        if not os.path.exists(output_path + "/" + host):
            os.makedirs(output_path + "/" + host)

        client = SSHClient(host, user, "netconf", debug=debug)
        client.connect()

        # Read the initial hello message
        client.read_hello()

        # Answer the hello message
        client.write_command(client.netconf_hello)

        # Send the state request
        client.write_command(client.netconf_state)

        # Read the state data
        data = client.read_command_output()

        # Parse the state data
        states = client.parse_netconf_state(data)

        yang_largest = 0
        yang_largest_name = ""
        yang_smallest = 0
        yang_smallest_name = ""
        yang_total = 0
        yang_num = 0

        # Get the schema for each state
        time_start = time.time()

        for state in states:
            schema = client.get_netconf_schema(state[0], state[1])
            size = client.parse_netconf_schema_yang(
                schema, state[0], state[1], output_path + "/" + host
            )

            if yang_largest < size:
                yang_largest = size
                yang_largest_name = state[0] + "@" + state[1]

            if yang_smallest > size or yang_smallest == 0:
                yang_smallest = size
                yang_smallest_name = state[0] + "@" + state[1]

            yang_num += 1
            yang_total += size

        time_end = time.time()

        print("")
        print(f"({host}) YANG Modules: {yang_num}")
        print(f"({host}) YANG Largest: {yang_largest_name} ({yang_largest} bytes)")
        print(f"({host}) YANG Smallest: {yang_smallest_name} ({yang_smallest} bytes)")
        print(f"({host}) Total YANG size: {yang_total} bytes")
        print(f"({host}) Duration: {time_end - time_start:.2f} seconds")

    compare_checksums(output_path)


if __name__ == "__main__":
    main()
