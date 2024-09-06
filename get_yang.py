import os
import subprocess
import sys
import xml.etree.ElementTree as ET


class SSHClient:
    def __init__(self, host, user, subsystem=""):
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
        data = ""

        for line in self.client.stdout:
            data += line
            if "]]>]]>" in line:
                break

        data = data.replace("]]>]]>", "")

        return data

    def write_command(self, command):
        self.client.stdin.write(command + "\n")
        self.client.stdin.flush()

    def parse_netconf_state(self, data):
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
        command = self.netconf_get_schema.replace("{{IDENTIFIER}}", identifier)
        command = command.replace("{{VERSION}}", version)

        self.write_command(command)

        data = self.read_command_output()

        return data

    def parse_netconf_schema_yang(self, data, identifier, version, output_path):
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
    client.read_command_output()
    client.write_command(client.netconf_hello)
    client.write_command(client.netconf_state)

    data = client.read_command_output()

    states = client.parse_netconf_state(data)

    for state in states:
        schema = client.get_netconf_schema(state[0], state[1])
        client.parse_netconf_schema_yang(schema, state[0], state[1], output_path)


if __name__ == "__main__":
    main()
