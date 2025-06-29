# Copyright (c) ONNX Project Contributors
# SPDX-License-Identifier: Apache-2.0
"""Convenience methods for constructing and manipulating the IR.

This is an internal only module. We should choose to expose some of the methods
in convenience.py after they are proven to be useful.
"""

from __future__ import annotations

__all__ = [
    "convert_attribute",
    "convert_attributes",
    "replace_all_uses_with",
    "create_value_mapping",
    "replace_nodes_and_values",
    "get_const_tensor",
]

import logging
from collections.abc import Mapping, Sequence
from typing import Union

import numpy as np
import onnx  # noqa: TID251

from onnx_ir import _core, _enums, _protocols, serde, traversal

SupportedAttrTypes = Union[
    str,
    int,
    float,
    Sequence[int],
    Sequence[float],
    Sequence[str],
    _protocols.TensorProtocol,  # This includes all in-memory tensor types
    onnx.TensorProto,
    _core.Attr,
    _protocols.GraphProtocol,
    Sequence[_protocols.GraphProtocol],
    onnx.GraphProto,
    _protocols.TypeProtocol,
    Sequence[_protocols.TypeProtocol],
    None,
]


logger = logging.getLogger(__name__)


def _infer_attribute_type(attr: SupportedAttrTypes) -> _enums.AttributeType:
    """Infer the attribute type based on the type of the Python object."""
    if isinstance(attr, int):
        return _enums.AttributeType.INT
    if isinstance(attr, float):
        return _enums.AttributeType.FLOAT
    if isinstance(attr, str):
        return _enums.AttributeType.STRING
    if isinstance(attr, _core.Attr):
        return attr.type
    if isinstance(attr, Sequence) and all(isinstance(x, int) for x in attr):
        return _enums.AttributeType.INTS
    if isinstance(attr, Sequence) and all(isinstance(x, float) for x in attr):
        return _enums.AttributeType.FLOATS
    if isinstance(attr, Sequence) and all(isinstance(x, str) for x in attr):
        return _enums.AttributeType.STRINGS
    if isinstance(attr, (_core.TensorBase, onnx.TensorProto, _protocols.TensorProtocol)):
        # Be sure to check TensorProtocol last because isinstance checking on Protocols can be slower
        return _enums.AttributeType.TENSOR
    if isinstance(attr, Sequence) and all(
        isinstance(x, (_core.TensorBase, onnx.TensorProto, _protocols.TensorProtocol))
        for x in attr
    ):
        return _enums.AttributeType.TENSORS
    if isinstance(attr, (_core.Graph, onnx.GraphProto, _protocols.GraphProtocol)):
        return _enums.AttributeType.GRAPH
    if isinstance(attr, Sequence) and all(
        isinstance(x, (_core.Graph, onnx.GraphProto, _protocols.GraphProtocol)) for x in attr
    ):
        return _enums.AttributeType.GRAPHS
    if isinstance(
        attr,
        (_core.TensorType, _core.SequenceType, _core.OptionalType, _protocols.TypeProtocol),
    ):
        return _enums.AttributeType.TYPE_PROTO
    if isinstance(attr, Sequence) and all(
        isinstance(
            x,
            (
                _core.TensorType,
                _core.SequenceType,
                _core.OptionalType,
                _protocols.TypeProtocol,
            ),
        )
        for x in attr
    ):
        return _enums.AttributeType.TYPE_PROTOS
    raise TypeError(f"Unsupported attribute type: '{type(attr)}'")


def convert_attribute(
    name: str,
    attr: SupportedAttrTypes,
    attr_type: _enums.AttributeType | None = None,
) -> _core.Attr:
    """Convert a Python object to a _core.Attr object.

    This method is useful when constructing nodes with attributes. It infers the
    attribute type based on the type of the Python value.

    Args:
        name: The name of the attribute.
        attr: The value of the attribute.
        attr_type: The type of the attribute. This is required when attr is None.
            When provided, it overrides the inferred type.

    Returns:
        A ``Attr`` object.

    Raises:
        ValueError: If ``attr`` is ``None`` and ``attr_type`` is not provided.
        TypeError: If the type of the attribute is not supported.
    """
    if attr is None:
        if attr_type is None:
            raise ValueError("attr_type must be provided when attr is None")
        return _core.Attr(name, attr_type, None)

    if isinstance(attr, _core.Attr):
        if attr.name != name:
            raise ValueError(
                f"Attribute name '{attr.name}' does not match provided name '{name}'"
            )
        if attr_type is not None and attr.type != attr_type:
            raise ValueError(
                f"Attribute type '{attr.type}' does not match provided type '{attr_type}'"
            )
        return attr

    if attr_type is None:
        attr_type = _infer_attribute_type(attr)

    if attr_type == _enums.AttributeType.INT:
        return _core.AttrInt64(name, attr)  # type: ignore
    if attr_type == _enums.AttributeType.FLOAT:
        return _core.AttrFloat32(name, attr)  # type: ignore
    if attr_type == _enums.AttributeType.STRING:
        return _core.AttrString(name, attr)  # type: ignore
    if attr_type == _enums.AttributeType.INTS:
        return _core.AttrInt64s(name, attr)  # type: ignore
    if attr_type == _enums.AttributeType.FLOATS:
        return _core.AttrFloat32s(name, attr)  # type: ignore
    if attr_type == _enums.AttributeType.STRINGS:
        return _core.AttrStrings(name, attr)  # type: ignore
    if attr_type == _enums.AttributeType.TENSOR:
        if isinstance(attr, (_core.TensorBase, _protocols.TensorProtocol)):
            return _core.AttrTensor(name, attr)
        if isinstance(attr, onnx.TensorProto):
            return _core.AttrTensor(name, serde.deserialize_tensor(attr))
    if attr_type == _enums.AttributeType.TENSORS:
        tensors = []
        for t in attr:  # type: ignore[union-attr]
            if isinstance(t, onnx.TensorProto):
                tensors.append(_core.AttrTensor(name, serde.deserialize_tensor(t)))
            else:
                tensors.append(t)  # type: ignore[arg-type]
        return _core.AttrTensors(name, tensors)  # type: ignore[arg-type]
    if attr_type == _enums.AttributeType.GRAPH:
        if isinstance(attr, onnx.GraphProto):
            attr = serde.deserialize_graph(attr)
        return _core.AttrGraph(name, attr)  # type: ignore[arg-type]
    if attr_type == _enums.AttributeType.GRAPHS:
        graphs = []
        for graph in attr:  # type: ignore[union-attr]
            if isinstance(graph, onnx.GraphProto):
                graphs.append(serde.deserialize_graph(graph))
            else:
                graphs.append(graph)  # type: ignore[arg-type]
        return _core.AttrGraphs(name, graphs)  # type: ignore[arg-type]
    if attr_type == _enums.AttributeType.TYPE_PROTO:
        return _core.AttrTypeProto(name, attr)  # type: ignore[arg-type]
    if attr_type == _enums.AttributeType.TYPE_PROTOS:
        return _core.AttrTypeProtos(name, attr)  # type: ignore[arg-type]
    raise TypeError(f"Unsupported attribute type: '{type(attr)}'")


def convert_attributes(
    attrs: Mapping[str, SupportedAttrTypes],
) -> list[_core.Attr]:
    """Convert a dictionary of attributes to a list of _core.Attr objects.

    It infers the attribute type based on the type of the value. The supported
    types are: int, float, str, Sequence[int], Sequence[float], Sequence[str],
    :class:`_core.Tensor`, and :class:`_core.Attr`::

        >>> import onnx_ir as ir
        >>> import onnx
        >>> import numpy as np
        >>> attrs = {
        ...     "int": 1,
        ...     "float": 1.0,
        ...     "str": "hello",
        ...     "ints": [1, 2, 3],
        ...     "floats": [1.0, 2.0, 3.0],
        ...     "strings": ["hello", "world"],
        ...     "tensor": ir.Tensor(np.array([1.0, 2.0, 3.0])),
        ...     "tensor_proto":
        ...         onnx.TensorProto(
        ...             dims=[3],
        ...             data_type=onnx.TensorProto.FLOAT,
        ...             float_data=[1.0, 2.0, 3.0],
        ...             name="proto",
        ...         ),
        ...     "graph": ir.Graph([], [], nodes=[], name="graph0"),
        ...     "graphs": [ir.Graph([], [], nodes=[], name="graph1"), ir.Graph([], [], nodes=[], name="graph2")],
        ...     "type_proto": ir.TensorType(ir.DataType.FLOAT),
        ...     "type_protos": [ir.TensorType(ir.DataType.FLOAT), ir.TensorType(ir.DataType.FLOAT)],
        ... }
        >>> convert_attributes(attrs)
        [Attr('int', INT, 1), Attr('float', FLOAT, 1.0), Attr('str', STRING, 'hello'), Attr('ints', INTS, [1, 2, 3]), Attr('floats', FLOATS, [1.0, 2.0, 3.0]), Attr('strings', STRINGS, ['hello', 'world']), Attr('tensor', TENSOR, Tensor<DOUBLE,[3]>(array([1., 2., 3.]), name=None)), Attr('tensor_proto', TENSOR, TensorProtoTensor<FLOAT,[3]>(array([1., 2., 3.], dtype=float32), name='proto')), Attr('graph', INTS, Graph(
            name='graph0',
            inputs=(
        <BLANKLINE>
            ),
            outputs=(
        <BLANKLINE>
            ),
            len()=0
        )), Attr('graphs', GRAPHS, [Graph(
            name='graph1',
            inputs=(
        <BLANKLINE>
            ),
            outputs=(
        <BLANKLINE>
            ),
            len()=0
        ), Graph(
            name='graph2',
            inputs=(
        <BLANKLINE>
            ),
            outputs=(
        <BLANKLINE>
            ),
            len()=0
        )]), Attr('type_proto', TYPE_PROTO, Tensor(FLOAT)), Attr('type_protos', TYPE_PROTOS, [Tensor(FLOAT), Tensor(FLOAT)])]

    Args:
        attrs: A dictionary of {<attribute name>: <python objects>} to convert.

    Returns:
        A list of _core.Attr objects.
    """
    attributes: list[_core.Attr] = []
    for name, attr in attrs.items():
        if attr is not None:
            attributes.append(convert_attribute(name, attr))
    return attributes


def replace_all_uses_with(
    values: _protocols.ValueProtocol | Sequence[_protocols.ValueProtocol],
    replacements: _protocols.ValueProtocol | Sequence[_protocols.ValueProtocol],
) -> None:
    """Replace all uses of the given values with the replacements.

    This is useful when nodes in the graph are replaced with new nodes, where
    the old users need to be updated to use the outputs of the new nodes.

    For example, suppose we have the following graph::

        A -> {B, C}

    We want to replace the node A with a new node D::

        >>> import onnx_ir as ir
        >>> input = ir.Input("input")
        >>> node_a = ir.Node("", "A", [input])
        >>> node_b = ir.Node("", "B", node_a.outputs)
        >>> node_c = ir.Node("", "C", node_a.outputs)
        >>> node_d = ir.Node("", "D", [input])
        >>> replace_all_uses_with(node_a.outputs, node_d.outputs)
        >>> len(node_b.inputs)
        1
        >>> node_b.inputs[0].producer().op_type
        'D'
        >>> len(node_c.inputs)
        1
        >>> node_c.inputs[0].producer().op_type
        'D'
        >>> len(node_a.outputs[0].uses())
        0

    When values and replacements are sequences, they are zipped into pairs. All
    users of the first value is replaced with the first replacement, and so on.

    .. note::
        You still need to update the graph outputs if any of the values being
        replaced are part of the graph outputs. Be sure to remove the old nodes
        from the graph using ``graph.remove()`` if they are no longer needed.

    Args:
        values: The value or values to be replaced.
        replacements: The new value or values to use as inputs.
    """
    if not isinstance(values, Sequence):
        values = (values,)
    if not isinstance(replacements, Sequence):
        replacements = (replacements,)
    if len(values) != len(replacements):
        raise ValueError("The number of values and replacements must match.")
    for value, replacement in zip(values, replacements):
        for user_node, index in tuple(value.uses()):
            user_node.replace_input_with(index, replacement)


def create_value_mapping(graph: _core.Graph) -> dict[str, _core.Value]:
    """Return a dictionary mapping names to values in the graph.

    The mapping includes values from subgraphs. Duplicated names are omitted,
    and the first value with that name is returned. Values with empty names
    are excluded from the mapping.

    .. versionchanged:: 0.1.2
        Values from subgraphs are now included in the mapping.

    Args:
        graph: The graph to extract the mapping from.

    Returns:
        A dictionary mapping names to values.
    """
    values: dict[str, _core.Value] = {}
    values.update(graph.initializers)
    # The names of the values can be None or "", which we need to exclude
    for input in graph.inputs:
        if not input.name:
            continue
        if input.name in values:
            continue
        values[input.name] = input
    for node in traversal.RecursiveGraphIterator(graph):
        for value in node.inputs:
            if not value:
                continue
            if not value.name:
                continue
            if value.name in values:
                continue
            values[value.name] = value
        for value in node.outputs:
            if not value.name:
                continue
            if value.name in values:
                continue
            values[value.name] = value
    return values


def replace_nodes_and_values(
    graph_or_function: _core.Graph | _core.Function,
    /,
    insertion_point: _core.Node,
    old_nodes: Sequence[_core.Node],
    new_nodes: Sequence[_core.Node],
    old_values: Sequence[_core.Value],
    new_values: Sequence[_core.Value],
) -> None:
    """Replaces nodes and values in the graph or function.

    Args:
        graph_or_function: The graph or function to replace nodes and values in.
        insertion_point: The node to insert the new nodes after.
        old_nodes: The nodes to replace.
        new_nodes: The nodes to replace with.
        old_values: The values to replace.
        new_values: The values to replace with.
    """
    for old_value, new_value in zip(old_values, new_values):
        # Propagate relevant info from old value to new value
        # TODO(Rama): Perhaps this should be a separate utility function. Also, consider
        # merging old and new type/shape info.
        new_value.type = old_value.type
        new_value.shape = old_value.shape
        new_value.const_value = old_value.const_value
        new_value.name = old_value.name

    # Reconnect the users of the deleted values to use the new values
    replace_all_uses_with(old_values, new_values)
    # Update graph/function outputs if the node generates output
    replacement_mapping = dict(zip(old_values, new_values))
    for idx, graph_or_function_output in enumerate(graph_or_function.outputs):
        if graph_or_function_output in replacement_mapping:
            graph_or_function.outputs[idx] = replacement_mapping[graph_or_function_output]

    # insert new nodes after the index node
    graph_or_function.insert_after(insertion_point, new_nodes)
    graph_or_function.remove(old_nodes, safe=True)


def get_const_tensor(
    value: _core.Value, propagate_shape_type: bool = False
) -> _protocols.TensorProtocol | None:
    """Get the constant tensor from a value, if it exists.

    A constant tensor can be obtained if the value has a ``const_value`` set
    (as in the case of an initializer) or if the value is produced by a
    Constant node.

    This function will not alter the ``const_value`` of the value, but
    it will propagate the shape and type of the constant tensor to the value
    if `propagate_shape_type` is set to True.

    .. versionadded:: 0.1.2

    Args:
        value: The value to get the constant tensor from.
        propagate_shape_type: If True, the shape and type of the value will be
            propagated to the Value.

    Returns:
        The constant tensor if it exists, otherwise None.

    Raises:
        ValueError: If the Constant node does not have exactly one output or
            one attribute.
    """
    tensor = None
    if value.const_value is not None:
        tensor = value.const_value
    else:
        node = value.producer()
        if node is None:
            # Potentially a graph input
            return None
        if node.op_type != "Constant" or node.domain != "":
            # Not a Constant node or not in the ONNX domain
            return None
        if len(node.outputs) != 1:
            raise ValueError(
                f"Constant node '{node.name}' must have exactly one output, "
                f"but has {len(node.outputs)} outputs."
            )
        if len(node.attributes) != 1:
            raise ValueError(
                f"Constant node '{node.name}' must have exactly one attribute, "
                f"but has {len(node.attributes)} attributes."
            )

        attr_name, attr_value = next(iter(node.attributes.items()))

        if attr_value.is_ref():
            # TODO: Make it easier to resolve a reference attribute.
            # For now we just return None
            return None

        ir_value = node.outputs[0]
        if attr_name in {"value_float", "value_floats"}:
            tensor = _core.Tensor(
                np.array(attr_value.value, dtype=np.float32), name=ir_value.name
            )
        elif attr_name in {"value_int", "value_ints"}:
            tensor = _core.Tensor(
                np.array(attr_value.value, dtype=np.int64), name=ir_value.name
            )
        elif attr_name in {"value_string", "value_strings"}:
            tensor = _core.StringTensor(
                np.array(attr_value.value, dtype=np.bytes_), name=ir_value.name
            )
        elif attr_name == "value":
            tensor = attr_value.as_tensor()
        else:
            raise ValueError(
                f"Unsupported attribute '{attr_name}' in Constant node '{node.name}'. "
                "Expected one of 'value_float', 'value_floats', 'value_int', "
                "'value_ints', 'value_string', 'value_strings', or 'value'."
            )
        # Assign the name of the constant value to the tensor
        tensor.name = value.name
    if tensor is not None and propagate_shape_type:
        # Propagate the shape and type of the tensor to the value
        if value.shape is not None and value.shape != tensor.shape:
            logger.warning(
                "Value '%s' has a shape %s that differs from "
                "the constant tensor's shape %s. The value's shape will be updated.",
                value,
                value.shape,
                tensor.shape,
            )
        value.shape = tensor.shape  # type: ignore[assignment]
        new_value_type = _core.TensorType(tensor.dtype)
        if value.type is not None and value.type != new_value_type:
            logger.warning(
                "Value '%s' has a type '%s' that differs from "
                "the constant tensor's type '%s'. The value's type will be updated.",
                value,
                value.type,
                new_value_type,
            )
        value.type = new_value_type
    return tensor
