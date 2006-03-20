# epydoc -- Graph generation
#
# Copyright (C) 2005 Edward Loper
# Author: Edward Loper <edloper@loper.org>
# URL: <http://epydoc.sf.net>
#
# $Id: docparser.py 1015 2006-03-19 03:27:50Z edloper $

"""
Render Graphviz directed graphs as images.  Below are some examples.

.. importgraph::

.. classtree:: epydoc.apidoc.APIDoc

.. packagetree:: epydoc

:see: `The Graphviz Homepage
       <http://www.research.att.com/sw/tools/graphviz/>`__
"""
__docformat__ = 'restructuredtext'

from sets import Set
import re
from epydoc import log
from epydoc.apidoc import DottedName, ModuleDoc

# Backwards compatibility imports:
try: sorted
except NameError: from epydoc.util import py_sorted as sorted

######################################################################
#{ Dot Graphs
######################################################################

DOT_COMMAND = 'dot'
"""The command that should be used to spawn dot"""

class DotGraph:
    """
    A `dot` directed graph.  The contents of the graph are
    constructed from the following instance variables:

      - `nodes`: A list of `DotGraphNode`\\s, encoding the nodes
        that are present in the graph.  Each node is characterized
        a set of attributes, including an optional label.
      - `edges`: A list of `DotGraphEdge`\\s, encoding the edges
        that are present in the graph.  Each edge is characterized
        by a set of attributes, including an optional label.
      - `node_defaults`: Default attributes for nodes.
      - `edge_defaults`: Default attributes for edges.
      - `body`: A string that is appended as-is in the body of
        the graph.  This can be used to build more complex dot
        graphs.

    The `link()` method can be used to resolve crossreference links
    within the graph.  In particular, if the 'href' attribute of any
    node or edge is assigned a value of the form `<name>`, then it
    will be replaced by the URL of the object with that name.  This
    applies to the `body` as well as the `nodes` and `edges`.

    To render the graph, use the methods `write()` and `render()`.
    Usually, you should call `link()` before you render the graph.
    """
    _uids = Set()
    """A set of all uids that that have been generated, used to ensure
    that each new graph has a unique uid."""

    def __init__(self, title, body='', node_defaults=None, edge_defaults=None):
        """
        Create a new `DotGraph`.
        """
        self.title = title
        """The title of the graph."""
        
        self.nodes = []
        """A list of the nodes that are present in the graph.
        :type: `list` of `DocGraphNode`"""
        
        self.edges = []
        """A list of the edges that are present in the graph.
        :type: `list` of `DocGraphEdge`"""

        self.body = body
        """A string that should be included as-is in the body of the
        graph.
        :type: `str`"""
        
        self.node_defaults = node_defaults or {}
        """Default attribute values for nodes."""
        
        self.edge_defaults = edge_defaults or {}
        """Default attribute values for edges."""

        self.uid = re.sub(r'\W', '_', title).lower()
        """A unique identifier for this graph.  This can be used as a
        filename when rendering the graph.  No two `DotGraph`s will
        have the same uid."""

        # Make sure the UID is unique
        if self.uid in self._uids:
            n = 2
            while ('%s_%s' % (self.uid, n)) in self._uids: n += 1
            self.uid = '%s_%s' % (self.uid, n)
        self._uids.add(self.uid)

    def link(self, docstring_linker):
        """
        Replace any href attributes whose value is <name> with 
        the url of the object whose name is <name>.
        """
        # Link xrefs in nodes
        self._link_href(self.node_defaults, docstring_linker)
        for node in self.nodes:
            self._link_href(node.attribs, docstring_linker)

        # Link xrefs in edges
        self._link_href(self.edge_defaults, docstring_linker)
        for edge in self.nodes:
            self._link_href(edge.attribs, docstring_linker)

        # Link xrefs in body
        def subfunc(m):
            url = docstring_linker.url_for(m.group(1))
            if url: return 'href="%s"%s' % (url, m.group(2))
            else: return ''
        self.body = re.sub("href\s*=\s*['\"]?<([\w\.]+)>['\"]?\s*(,?)",
                           subfunc, self.body)

    def _link_href(self, attribs, docstring_linker):
        """Helper for `link()`"""
        if 'href' in attribs:
            m = re.match(r'^<([\w\.]+)>$', attribs['href'])
            if m:
                url = docstring_linker.url_for(m.group(1))
                if url: attribs['href'] = url
                else: del attribs['href']
                
    def write(self, filename, language='gif'):
        """
        Render the graph using the output format `language`, and write
        the result to `filename`.
        :return: True if rendering was successful.
        """
        s = self.render(language)
        if s is not None:
            out = open(filename, 'w')
            out.write(s)
            out.close()
            return True
        else:
            return False

    def render(self, language='gif'):
        """
        Use the `dot` command to render this graph, using the output
        format `language`.  Return the result as a string, or `None`
        if the rendering failed.
        """
        try:
            from subprocess import Popen, PIPE
            cmd = [DOT_COMMAND, '-T%s' % language]
            pipe = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                         close_fds=True)
            (to_child, from_child) = (pipe.stdin, pipe.stdout)
        except ImportError:
            from popen2 import Popen4
            cmd = '%s -T%s' % (DOT_COMMAND, language)
            pipe = Popen4(cmd)
            (to_child, from_child) = (pipe.tochild, pipe.fromchild)

        to_child.write(self.to_dotfile())
        to_child.close()
        result = ''
        while pipe.poll() is None:
            result += from_child.read()
        result += from_child.read()
        exitval = pipe.wait()
        
        if exitval:
            log.warning("Unable to render Graphviz dot graph:\n%s" %
                        from_child.read())
            return None

        return result

    def to_dotfile(self):
        """
        Return the string contents of the dot file that should be used
        to render this graph.
        """
        lines = ['digraph %s {' % self.uid,
                 'node [%s]' % ','.join(['%s="%s"' % (k,v) for (k,v)
                                         in self.node_defaults.items()]),
                 'edge [%s]' % ','.join(['%s="%s"' % (k,v) for (k,v)
                                         in self.edge_defaults.items()])]
        if self.body:
            lines.append(self.body)
        lines.append('/* Nodes */')
        for node in self.nodes:
            lines.append(node.to_dotfile())
        lines.append('/* Edges */')
        for edge in self.edges:
            lines.append(edge.to_dotfile())
        lines.append('}')
        return '\n'.join(lines)

class DotGraphNode:
    _next_id = 0
    def __init__(self, label=None, **attribs):
        if label is not None: attribs['label'] = label
        self.attribs = attribs
        self.id = self.__class__._next_id
        self.__class__._next_id += 1

    def to_dotfile(self):
        """
        Return the dot commands that should be used to render this node.
        """
        attribs = ','.join(['%s="%s"' % (k,v) for (k,v)
                            in self.attribs.items()])
        if attribs: attribs = ' [%s]' % attribs
        return 'node%d%s' % (self.id, attribs)

class DotGraphEdge:
    def __init__(self, start, end, label=None, **attribs):
        """
        :type start: `DotGraphNode`
        :type end: `DotGraphNode`
        """
        if label is not None: attribs['label'] = label
        self.start = start       #: :type: `DotGraphNode`
        self.end = end           #: :type: `DotGraphNode`
        self.attribs = attribs

    def to_dotfile(self):
        """
        Return the dot commands that should be used to render this edge.
        """
        attribs = ','.join(['%s="%s"' % (k,v) for (k,v)
                            in self.attribs.items()])
        if attribs: attribs = ' [%s]' % attribs
        return 'node%d -> node%d%s' % (self.start.id, self.end.id, attribs)

######################################################################
#{ Graph Generation Functions
######################################################################

def package_tree_graph(packages, linker, context=None, **options):
    """
    Return a `DotGraph` that graphically displays the package
    hierarchies for the given packages.
    """
    graph = DotGraph('Package Tree',
                     node_defaults={'shape':'box', 'width': 0, 'height': 0},
                     edge_defaults={'sametail':True})
    
    # Options
    if options.get('dir', 'LR') != 'TB':
        graph.body += 'rankdir=%s\n' % options.get('dir', 'LR')

    # Get a list of all modules in the package.
    queue = list(packages)
    modules = Set(packages)
    for module in queue:
        queue.extend(module.submodules)
        modules.update(module.submodules)

    # Add a node for each module.
    nodes = add_valdoc_nodes(graph, modules, linker, context)

    # Add an edge for each package/submodule relationship.
    for module in modules:
        for submodule in module.submodules:
            graph.edges.append(DotGraphEdge(nodes[module], nodes[submodule]))

    return graph

def class_tree_graph(bases, linker, context=None, **options):
    """
    Return a `DotGraph` that graphically displays the package
    hierarchies for the given packages.
    """
    graph = DotGraph('Class Hierarchy',
                     node_defaults={'shape':'box', 'width': 0, 'height': 0},
                     edge_defaults={'sametail':True})

    # Options
    if options.get('dir', 'LR') != 'TB':
        graph.body += 'rankdir=%s\n' % options.get('dir', 'LR')

    # Get a list of all classes derived from the given base(s).
    queue = list(bases)
    classes = Set(bases)
    for cls in queue:
        queue.extend(cls.subclasses)
        classes.update(cls.subclasses)

    # Add a node for each cls.
    nodes = add_valdoc_nodes(graph, classes, linker, context)

    # Add an edge for each package/subclass relationship.
    for cls in classes:
        for subcls in cls.subclasses:
            graph.edges.append(DotGraphEdge(nodes[cls], nodes[subcls]))

    return graph

def import_graph(modules, docindex, linker, context=None, **options):
    graph = DotGraph('Import Graph',
                     node_defaults={'shape':'box', 'width': 0, 'height': 0},
                     edge_defaults={'sametail':True})

    # Options
    if options.get('dir', 'RL') != 'TB': # default: right-to-left.
        graph.body += 'rankdir=%s\n' % options.get('dir', 'RL')

    # Add a node for each module.
    nodes = add_valdoc_nodes(graph, modules, linker, context)

    # Edges.
    edges = Set()
    for dst in modules:
        for var_name in dst.imports:
            for i in range(len(var_name), 0, -1):
                val_doc = docindex.get_valdoc(DottedName(*var_name[:i]))
                if isinstance(val_doc, ModuleDoc):
                    edges.add( (val_doc, dst) )
                    break

    for (src, dst) in edges:
        if src in nodes and dst in nodes:
            graph.edges.append(DotGraphEdge(nodes[src], nodes[dst]))

    return graph
    
# [xx] Use short names when possible, but long names when needed?
def add_valdoc_nodes(graph, val_docs, linker, context):
    nodes = {}
    val_docs = sorted(val_docs, key=lambda d:d.canonical_name)
    for i, val_doc in enumerate(val_docs):
        node = nodes[val_doc] = DotGraphNode(val_doc.canonical_name)
        graph.nodes.append(node)
        if val_doc == context:
            node.attribs.update({'fillcolor':'black', 'fontcolor':'white',
                                 'style':'filled'})
        else:
            url = linker.url_for(val_doc)
            if url: node.attribs['href'] = url
    return nodes
