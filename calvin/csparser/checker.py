# -*- coding: utf-8 -*-

# Copyright (c) 2015 Ericsson AB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from calvin.csparser.parser import calvin_parser
from calvin.actorstore.store import DocumentationStore
import json

class Checker(object):
    # FIXME: Provide additional checks making use of
    #        - actor_def.inport_names and actor_def.outport_names
    #        - make use of arg_type (STRING, NUMBER, etc.)
    #        - analyze the actions wrt port use and token consumption:
    #          for f in actor_def.action_priority:
    #              print f.__name__, [x.cell_contents for x in f.__closure__]
    #
    def __init__(self, cs_info):
        super(Checker, self).__init__()
        self.ds = DocumentationStore()
        self.cs_info = cs_info
        self.local_actors = {}
        self.errors = []
        self.warnings = []
        self.check()

    def issue(self, fmt, **info):
        return {'reason':fmt.format(**info), 'line':info.get('line', 0), 'col':info.get('col', 0)}

    def append_error(self, fmt, **info):
        issue = self.issue(fmt, **info)
        self.errors.append(issue)

    def append_warning(self, fmt, **info):
        issue = self.issue(fmt, **info)
        self.warnings.append(issue)

    def check(self):
        components = self.cs_info['components']
        for comp in components:
            self.local_actors[comp['name']] = comp
            self.check_component(comp)
        self.check_structure(self.cs_info['structure'])

    def check_component(self, comp_def):
        # print comp_name, json.dumps(comp_def, indent=4), json.dumps(self.get_definition(comp_name), indent=4)
        # fake definition for component test inputs/outputs have reversed meaning
        # defs = {'inputs':[(p, '') for p in comp_def['outports']], 'outputs':[(p, '') for p in comp_def['inports']]}
        defs = self.get_definition(comp_def['name'])
        self.check_connections(None, defs, comp_def['structure']['connections'])
        self.check_structure(comp_def['structure'])
        # Check for unused arguments and issue warning, not error
        args = set(comp_def['arg_identifiers'])
        used_args = set([])
        for a in comp_def['structure']['actors'].values():
            used_args.update(a['args'].keys())
        unused_args = args - used_args
        for u in unused_args:
            fmt = "Unused argument: '{param}'"
            self.append_warning(fmt, line=comp_def['dbg_line'], param=u)

    def get_definition(self, actor_type):
        if actor_type in self.local_actors:
            return self.ds.component_docs("local."+actor_type, self.local_actors[actor_type])
        return self.ds.actor_docs(actor_type)

    def dbg_lines(self, s):
        try:
            return [x['dbg_line'] for x in s] + [0]
        except:
            return [0]

    def check_component_connections(self, definition, connections):
        inport_names = [p for p, _ in definition['inputs']]
        outport_names = [p for p, _ in definition['outputs']]
        # Verify names of ports
        invalid_inports = [(c['src_port'], 'in', c['dbg_line']) for c in connections if not c['src'] and c['src_port'] not in inport_names]
        invalid_outports = [(c['dst_port'], 'out', c['dbg_line']) for c in connections if not c['dst'] and c['dst_port'] not in outport_names]
        invalid_ports = invalid_inports + invalid_outports
        for port, port_dir, line in invalid_ports:
            fmt = "Component {name} has no {port_dir}port '{port}'"
            self.append_error(fmt, line=line, port=port, port_dir=port_dir, **definition)
        # outports should have exactly one connection
        for port in outport_names:
            incoming = [c for c in connections if not c['dst'] and c['dst_port'] == port]
            if len(incoming) == 0:
                fmt = "Component {name} is missing connection to outport '{port}'"
                self.append_error(fmt, line=max(self.dbg_lines(connections)), port=port, **definition)
            if len(incoming) > 1:
                fmt = "Component {name} has multiple connections to outport '{port}'"
                for c in incoming:
                    self.append_error(fmt, line=c['dbg_line'], port=port, **definition)
        # inports should have at least one connection
        for port in inport_names:
            outgoing = [c for c in connections if not c['src'] and c['src_port'] == port]
            if len(outgoing) < 1:
                fmt = "Component {name} is missing connection to inport '{port}'"
                self.append_error(fmt, line=max(self.dbg_lines(connections)), port=port, **definition)

    def check_actor_connections(self, actor, definition, connections):
        inport_names = [p for p, _ in definition['inputs']]
        outport_names = [p for p, _ in definition['outputs']]
        # Verify names of ports
        invalid_inports = [(c['dst_port'], 'in', c['dbg_line']) for c in connections if c['dst'] == actor and c['dst_port'] not in inport_names]
        invalid_outports = [(c['src_port'], 'out', c['dbg_line']) for c in connections if c['src'] == actor and c['src_port'] not in outport_names]
        invalid_ports = invalid_inports + invalid_outports
        for port, port_dir, line in invalid_ports:
            fmt = "Actor {actor} ({ns}.{name}) has no {port_dir}port '{port}'"
            self.append_error(fmt, line=line, port=port, port_dir=port_dir, actor=actor, **definition)
        # inports should have exactly one connection
        for port in inport_names:
            incoming = [c for c in connections if c['dst'] == actor and c['dst_port'] == port]
            if len(incoming) == 0:
                fmt = "Actor {actor} ({ns}.{name}) is missing connection to inport '{port}'"
                self.append_error(fmt, line=max(self.dbg_lines(connections)), port=port, actor=actor, **definition)
            if len(incoming) > 1:
                fmt = "Actor {actor} ({ns}.{name}) has multiple connections to inport '{port}'"
                for c in incoming:
                    self.append_error(fmt, line=c['dbg_line'], port=port, actor=actor, **definition)
        # outports should have at least one connection
        for port in outport_names:
            outgoing = [c for c in connections if c['src'] == actor and c['src_port'] == port]
            if not outgoing:
                fmt = "Actor {actor} ({ns}.{name}) is missing connection to outport '{port}'"
                self.append_error(fmt, line=max(self.dbg_lines(connections)), port=port, actor=actor, **definition)

    def check_connections(self, actor, definition, connections):
        if actor:
            self.check_actor_connections(actor, definition, connections)
        else:
            self.check_component_connections(definition, connections)

    def check_arguments(self, definition, declaration):
        mandatory = set(definition['args']['mandatory'])
        defined = set(declaration['args'].keys())
        undefined = mandatory - defined
        for u in undefined:
            fmt = "Missing argument: '{param}'"
            self.append_error(fmt, line=declaration['dbg_line'], param=u)
            print self.errors[-1], definition

    def check_structure(self, structure):
        actors = structure['actors'].keys()

        # Look for undefined actors
        src_actors = {c['src'] for c in structure['connections'] if c['src']}
        dst_actors = {c['dst'] for c in structure['connections'] if c['dst']}
        all_actors = src_actors | dst_actors
        undefined_actors = all_actors - set(actors)
        for actor in undefined_actors:
            fmt = "Undefined actor: '{actor}'"
            lines = [c['dbg_line'] for c in structure['connections'] if c['src'] == actor or c['dst'] == actor]
            for line in lines:
                self.append_error(fmt, line=line, actor=actor)

        # Note: Unused actors will be caught when checking connections

        # Check if actor exists
        for actor in actors:
            actor_type = structure['actors'][actor]['actor_type']
            definition = self.get_definition(actor_type)
            if not definition:
                fmt = "Unknown actor type: '{type}'"
                self.append_error(fmt, type=actor_type, line=structure['actors'][actor]['dbg_line'])
                continue
            # We have actor definition, check that it is fully connected
            self.check_connections(actor, definition, structure['connections'])
            self.check_arguments(definition, structure['actors'][actor])


def check(cs_info):
    clint = Checker(cs_info)
    return clint.errors, clint.warnings


if __name__ == '__main__':
    import sys
    import os
    import json

    if len(sys.argv) < 2:
        script = 'inline'
        source_text = \
"""# Test script
component Foo() in -> out {

  x:std.Foo()

  in > x.in
  x.out > out
}

a:Foo()
b:io.StandardOut()
"""
    else:
        script = sys.argv[1]
        script = os.path.expanduser(script)
        try:
            with open(script, 'r') as source:
                source_text = source.read()
        except:
            print "Error: Could not read file: '%s'" % script
            sys.exit(1)

    result, errors, warnings = calvin_parser(source_text, script)
    if errors:
        print "{reason} {script} [{line}:{col}]".format(script=script, **error)
    else:
        errors, warnings = check(result)
        print "errors:", [x['reason'] for x in errors]
        print "warnings:", [x['reason'] for x in warnings]
