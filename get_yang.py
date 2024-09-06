import os
import subprocess
import sys
import xml.etree.ElementTree as ET

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

    def __init__(self, host, user, subsystem=""):
        """Initialize the SSH client."""
        self.host = host
        self.user = user
        self.subsystem = subsystem
        self.client = None

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

        self.client = subprocess.Popen(
            cmd_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            universal_newlines=True,
        )

    def read_command_output(self):
        """
        Read the output until we hit the "]]>]]>" delimiter. This delimiter is
        used by NETCONF to separate the XML data from the NETCONF framing.
        """

        data = ""

        for line in self.client.stdout:
            data += line
            if "]]>]]>" in line:
                break

        data = data.replace("]]>]]>", "")

        return data

    def write_command(self, command):
        """
        Write a command to the SSH client. The command should be a string
        containing a valid XML NETCONF message.
        """

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

            schemas.append((identifier, version, yangformat))

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

        print(f"Writing to {output_path}")

        with open(output_path, "w") as f:
            f.write(data)


def main():
    if len(sys.argv) != 4:
        print("Usage: get_yang.py <host> <user> <output_path>")
        sys.exit(1)

    host = sys.argv[1]
    user = sys.argv[2]
    output_path = sys.argv[3]

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    client = SSHClient(host, user, "netconf")
    client.connect()

    # Read the initial hello message
    client.read_command_output()

    # Answer the hello message
    client.write_command(client.netconf_hello)

    # Send the state request
    client.write_command(client.netconf_state)

    # Read the state data
    data = client.read_command_output()

    # Parse the state data
    states = client.parse_netconf_state(data)

    # Get the schema for each state
    for state in states:
        schema = client.get_netconf_schema(state[0], state[1])
        client.parse_netconf_schema_yang(schema, state[0], state[1], output_path)


if __name__ == "__main__":
    main()
