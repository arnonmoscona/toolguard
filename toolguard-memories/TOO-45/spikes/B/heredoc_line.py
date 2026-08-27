# This file was generated from heredoc_line.peg
# See https://canopy.jcoglan.com/ for documentation

from collections import defaultdict
import re


class TreeNode(object):
    def __init__(self, text, offset, elements):
        self.text = text
        self.offset = offset
        self.elements = elements

    def __iter__(self):
        for el in self.elements:
            yield el


class TreeNode1(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode1, self).__init__(text, offset, elements)
        self.spacing = elements[4]
        self.compound = elements[1]
        self.pipeline = elements[1]


class TreeNode2(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode2, self).__init__(text, offset, elements)
        self.control_op = elements[0]
        self.pipeline = elements[1]


class TreeNode3(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode3, self).__init__(text, offset, elements)
        self.spacing = elements[2]


class TreeNode4(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode4, self).__init__(text, offset, elements)
        self.spacing = elements[2]


class TreeNode5(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode5, self).__init__(text, offset, elements)
        self.spacing = elements[3]


class TreeNode6(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode6, self).__init__(text, offset, elements)
        self.spacing = elements[3]


class TreeNode7(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode7, self).__init__(text, offset, elements)
        self.spacing = elements[2]


class TreeNode8(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode8, self).__init__(text, offset, elements)
        self.command = elements[0]


class TreeNode9(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode9, self).__init__(text, offset, elements)
        self.pipe = elements[0]
        self.command = elements[1]


class TreeNode10(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode10, self).__init__(text, offset, elements)
        self.spacing = elements[3]


class TreeNode11(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode11, self).__init__(text, offset, elements)
        self.head = elements[0]
        self.word = elements[0]
        self.tail = elements[1]


class TreeNode12(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode12, self).__init__(text, offset, elements)
        self.spacing = elements[0]


class TreeNode13(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode13, self).__init__(text, offset, elements)
        self.strip = elements[2]
        self.spacing = elements[3]
        self.delimiter = elements[4]
        self.heredoc_delimiter = elements[4]


class TreeNode14(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode14, self).__init__(text, offset, elements)
        self.spacing = elements[2]
        self.target = elements[3]
        self.word = elements[3]


class TreeNode15(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode15, self).__init__(text, offset, elements)
        self.spacing = elements[3]
        self.target = elements[4]
        self.word = elements[4]


class TreeNode16(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode16, self).__init__(text, offset, elements)
        self.spacing = elements[3]
        self.target = elements[4]
        self.word = elements[4]


class TreeNode17(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode17, self).__init__(text, offset, elements)
        self.fd_num = elements[2]


class TreeNode18(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode18, self).__init__(text, offset, elements)
        self.paren_body = elements[1]


FAILURE = object()


class Grammar(object):
    REGEX_1 = re.compile("^[A-Za-z_]")
    REGEX_2 = re.compile("^[A-Za-z0-9_]")
    REGEX_3 = re.compile("^[0-9]")
    REGEX_4 = re.compile("^[ \\t|&;<>()\"'`]")
    REGEX_5 = re.compile("^[ \\t]")

    def _read_line(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["line"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_pipeline()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2, elements1, address4 = self._offset, [], None
                while True:
                    index3, elements2 = self._offset, []
                    address5 = FAILURE
                    address5 = self._read_control_op()
                    if address5 is not FAILURE:
                        elements2.append(address5)
                        address6 = FAILURE
                        address6 = self._read_pipeline()
                        if address6 is not FAILURE:
                            elements2.append(address6)
                        else:
                            elements2 = None
                            self._offset = index3
                    else:
                        elements2 = None
                        self._offset = index3
                    if elements2 is None:
                        address4 = FAILURE
                    else:
                        address4 = TreeNode2(
                            self._input[index3 : self._offset], index3, elements2
                        )
                        self._offset = self._offset
                    if address4 is not FAILURE:
                        elements1.append(address4)
                    else:
                        break
                if len(elements1) >= 0:
                    address3 = TreeNode(
                        self._input[index2 : self._offset], index2, elements1
                    )
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address7 = FAILURE
                    index4 = self._offset
                    address7 = self._read_trailing_op()
                    if address7 is FAILURE:
                        address7 = TreeNode(self._input[index4:index4], index4, [])
                        self._offset = index4
                    if address7 is not FAILURE:
                        elements0.append(address7)
                        address8 = FAILURE
                        address8 = self._read_spacing()
                        if address8 is not FAILURE:
                            elements0.append(address8)
                        else:
                            elements0 = None
                            self._offset = index1
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode1(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["line"][index0] = (address0, self._offset)
        return address0

    def _read_control_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["control_op"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_and_op()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_or_op()
            if address0 is FAILURE:
                self._offset = index1
                address0 = self._read_semicolon_op()
                if address0 is FAILURE:
                    self._offset = index1
                    address0 = self._read_background_op()
                    if address0 is FAILURE:
                        self._offset = index1
        self._cache["control_op"][index0] = (address0, self._offset)
        return address0

    def _read_and_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["and_op"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 2
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "&&":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 2], self._offset, []
                )
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::and_op", '"&&"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode3(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["and_op"][index0] = (address0, self._offset)
        return address0

    def _read_or_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["or_op"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 2
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "||":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 2], self._offset, []
                )
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::or_op", '"||"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode4(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["or_op"][index0] = (address0, self._offset)
        return address0

    def _read_semicolon_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["semicolon_op"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == ";":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::semicolon_op", '";"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == ";":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::semicolon_op", '";"'))
                self._offset = index2
                if address3 is FAILURE:
                    address3 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode5(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["semicolon_op"][index0] = (address0, self._offset)
        return address0

    def _read_background_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["background_op"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "&":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::background_op", '"&"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "&":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::background_op", '"&"'))
                self._offset = index2
                if address3 is FAILURE:
                    address3 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode6(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["background_op"][index0] = (address0, self._offset)
        return address0

    def _read_trailing_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["trailing_op"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2 = self._offset
            index3, elements1 = self._offset, []
            address3 = FAILURE
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "&":
                address3 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address3 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::trailing_op", '"&"'))
            if address3 is not FAILURE:
                elements1.append(address3)
                address4 = FAILURE
                index4 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "&":
                    address4 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address4 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::trailing_op", '"&"'))
                self._offset = index4
                if address4 is FAILURE:
                    address4 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address4 = FAILURE
                if address4 is not FAILURE:
                    elements1.append(address4)
                else:
                    elements1 = None
                    self._offset = index3
            else:
                elements1 = None
                self._offset = index3
            if elements1 is None:
                address2 = FAILURE
            else:
                address2 = TreeNode(
                    self._input[index3 : self._offset], index3, elements1
                )
                self._offset = self._offset
            if address2 is FAILURE:
                self._offset = index2
                chunk2, max2 = None, self._offset + 1
                if max2 <= self._input_size:
                    chunk2 = self._input[self._offset : max2]
                if chunk2 == ";":
                    address2 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address2 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::trailing_op", '";"'))
                if address2 is FAILURE:
                    self._offset = index2
            if address2 is not FAILURE:
                elements0.append(address2)
                address5 = FAILURE
                address5 = self._read_spacing()
                if address5 is not FAILURE:
                    elements0.append(address5)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode7(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["trailing_op"][index0] = (address0, self._offset)
        return address0

    def _read_pipeline(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["pipeline"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_command()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                index3, elements2 = self._offset, []
                address4 = FAILURE
                address4 = self._read_pipe()
                if address4 is not FAILURE:
                    elements2.append(address4)
                    address5 = FAILURE
                    address5 = self._read_command()
                    if address5 is not FAILURE:
                        elements2.append(address5)
                    else:
                        elements2 = None
                        self._offset = index3
                else:
                    elements2 = None
                    self._offset = index3
                if elements2 is None:
                    address3 = FAILURE
                else:
                    address3 = TreeNode9(
                        self._input[index3 : self._offset], index3, elements2
                    )
                    self._offset = self._offset
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(
                    self._input[index2 : self._offset], index2, elements1
                )
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode8(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["pipeline"][index0] = (address0, self._offset)
        return address0

    def _read_pipe(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["pipe"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "|":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::pipe", '"|"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "|":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::pipe", '"|"'))
                self._offset = index2
                if address3 is FAILURE:
                    address3 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode10(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["pipe"][index0] = (address0, self._offset)
        return address0

    def _read_command(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["command"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_word()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                index3, elements2 = self._offset, []
                address4 = FAILURE
                address4 = self._read_spacing()
                if address4 is not FAILURE:
                    elements2.append(address4)
                    address5 = FAILURE
                    index4 = self._offset
                    address5 = self._read_redirection()
                    if address5 is FAILURE:
                        self._offset = index4
                        address5 = self._read_word()
                        if address5 is FAILURE:
                            self._offset = index4
                    if address5 is not FAILURE:
                        elements2.append(address5)
                    else:
                        elements2 = None
                        self._offset = index3
                else:
                    elements2 = None
                    self._offset = index3
                if elements2 is None:
                    address3 = FAILURE
                else:
                    address3 = TreeNode12(
                        self._input[index3 : self._offset], index3, elements2
                    )
                    self._offset = self._offset
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(
                    self._input[index2 : self._offset], index2, elements1
                )
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode11(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["command"][index0] = (address0, self._offset)
        return address0

    def _read_redirection(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["redirection"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_heredoc()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_append_redirect()
            if address0 is FAILURE:
                self._offset = index1
                address0 = self._read_output_redirect()
                if address0 is FAILURE:
                    self._offset = index1
                    address0 = self._read_input_redirect()
                    if address0 is FAILURE:
                        self._offset = index1
                        address0 = self._read_stderr_to_stdout()
                        if address0 is FAILURE:
                            self._offset = index1
                            address0 = self._read_fd_redirect()
                            if address0 is FAILURE:
                                self._offset = index1
        self._cache["redirection"][index0] = (address0, self._offset)
        return address0

    def _read_heredoc(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["heredoc"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        index2 = self._offset
        address1 = self._read_fd_num()
        if address1 is FAILURE:
            address1 = TreeNode(self._input[index2:index2], index2, [])
            self._offset = index2
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 2
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "<<":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 2], self._offset, []
                )
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::heredoc", '"<<"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index3 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "-":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::heredoc", '"-"'))
                if address3 is FAILURE:
                    address3 = TreeNode(self._input[index3:index3], index3, [])
                    self._offset = index3
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        address5 = self._read_heredoc_delimiter()
                        if address5 is not FAILURE:
                            elements0.append(address5)
                        else:
                            elements0 = None
                            self._offset = index1
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode13(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["heredoc"][index0] = (address0, self._offset)
        return address0

    def _read_heredoc_delimiter(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["heredoc_delimiter"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_single_quoted()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_double_quoted()
            if address0 is FAILURE:
                self._offset = index1
                address0 = self._read_bare_delimiter()
                if address0 is FAILURE:
                    self._offset = index1
        self._cache["heredoc_delimiter"][index0] = (address0, self._offset)
        return address0

    def _read_bare_delimiter(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["bare_delimiter"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_1.search(chunk0):
            address1 = TreeNode(
                self._input[self._offset : self._offset + 1], self._offset, []
            )
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::bare_delimiter", "[A-Za-z_]"))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 is not None and Grammar.REGEX_2.search(chunk1):
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(
                            ("HeredocLine::bare_delimiter", "[A-Za-z0-9_]")
                        )
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(
                    self._input[index2 : self._offset], index2, elements1
                )
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["bare_delimiter"][index0] = (address0, self._offset)
        return address0

    def _read_append_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["append_redirect"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        index2 = self._offset
        address1 = self._read_fd_num()
        if address1 is FAILURE:
            address1 = TreeNode(self._input[index2:index2], index2, [])
            self._offset = index2
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 2
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == ">>":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 2], self._offset, []
                )
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::append_redirect", '">>"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_word()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode14(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["append_redirect"][index0] = (address0, self._offset)
        return address0

    def _read_output_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["output_redirect"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        index2 = self._offset
        address1 = self._read_fd_num()
        if address1 is FAILURE:
            address1 = TreeNode(self._input[index2:index2], index2, [])
            self._offset = index2
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == ">":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::output_redirect", '">"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index3 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == ">":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::output_redirect", '">"'))
                self._offset = index3
                if address3 is FAILURE:
                    address3 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        address5 = self._read_word()
                        if address5 is not FAILURE:
                            elements0.append(address5)
                        else:
                            elements0 = None
                            self._offset = index1
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode15(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["output_redirect"][index0] = (address0, self._offset)
        return address0

    def _read_input_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["input_redirect"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        index2 = self._offset
        address1 = self._read_fd_num()
        if address1 is FAILURE:
            address1 = TreeNode(self._input[index2:index2], index2, [])
            self._offset = index2
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "<":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::input_redirect", '"<"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index3 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "<":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::input_redirect", '"<"'))
                self._offset = index3
                if address3 is FAILURE:
                    address3 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        address5 = self._read_word()
                        if address5 is not FAILURE:
                            elements0.append(address5)
                        else:
                            elements0 = None
                            self._offset = index1
                    else:
                        elements0 = None
                        self._offset = index1
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode16(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["input_redirect"][index0] = (address0, self._offset)
        return address0

    def _read_stderr_to_stdout(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["stderr_to_stdout"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        chunk0, max0 = None, self._offset + 4
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "2>&1":
            address0 = TreeNode(
                self._input[self._offset : self._offset + 4], self._offset, []
            )
            self._offset = self._offset + 4
        else:
            address0 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::stderr_to_stdout", '"2>&1"'))
        self._cache["stderr_to_stdout"][index0] = (address0, self._offset)
        return address0

    def _read_fd_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["fd_redirect"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_fd_num()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2 = self._offset
            chunk0, max0 = None, self._offset + 2
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == ">&":
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 2], self._offset, []
                )
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::fd_redirect", '">&"'))
            if address2 is FAILURE:
                self._offset = index2
                chunk1, max1 = None, self._offset + 2
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "<&":
                    address2 = TreeNode(
                        self._input[self._offset : self._offset + 2], self._offset, []
                    )
                    self._offset = self._offset + 2
                else:
                    address2 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::fd_redirect", '"<&"'))
                if address2 is FAILURE:
                    self._offset = index2
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_fd_num()
                if address3 is not FAILURE:
                    elements0.append(address3)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode17(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["fd_redirect"][index0] = (address0, self._offset)
        return address0

    def _read_fd_num(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["fd_num"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 is not None and Grammar.REGEX_3.search(chunk0):
                address1 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address1 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::fd_num", "[0-9]"))
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 1:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache["fd_num"][index0] = (address0, self._offset)
        return address0

    def _read_word(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["word"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2 = self._offset
            address1 = self._read_quoted()
            if address1 is FAILURE:
                self._offset = index2
                address1 = self._read_opaque_subst()
                if address1 is FAILURE:
                    self._offset = index2
                    address1 = self._read_escaped_char()
                    if address1 is FAILURE:
                        self._offset = index2
                        index3, elements1 = self._offset, []
                        address2 = FAILURE
                        index4 = self._offset
                        address2 = self._read_delimiter()
                        self._offset = index4
                        if address2 is FAILURE:
                            address2 = TreeNode(
                                self._input[self._offset : self._offset],
                                self._offset,
                                [],
                            )
                            self._offset = self._offset
                        else:
                            address2 = FAILURE
                        if address2 is not FAILURE:
                            elements1.append(address2)
                            address3 = FAILURE
                            if self._offset < self._input_size:
                                address3 = TreeNode(
                                    self._input[self._offset : self._offset + 1],
                                    self._offset,
                                    [],
                                )
                                self._offset = self._offset + 1
                            else:
                                address3 = FAILURE
                                if self._offset > self._failure:
                                    self._failure = self._offset
                                    self._expected = []
                                if self._offset == self._failure:
                                    self._expected.append(
                                        ("HeredocLine::word", "<any char>")
                                    )
                            if address3 is not FAILURE:
                                elements1.append(address3)
                            else:
                                elements1 = None
                                self._offset = index3
                        else:
                            elements1 = None
                            self._offset = index3
                        if elements1 is None:
                            address1 = FAILURE
                        else:
                            address1 = TreeNode(
                                self._input[index3 : self._offset], index3, elements1
                            )
                            self._offset = self._offset
                        if address1 is FAILURE:
                            self._offset = index2
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 1:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache["word"][index0] = (address0, self._offset)
        return address0

    def _read_quoted(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["quoted"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_single_quoted()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_double_quoted()
            if address0 is FAILURE:
                self._offset = index1
        self._cache["quoted"][index0] = (address0, self._offset)
        return address0

    def _read_single_quoted(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["single_quoted"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "'":
            address1 = TreeNode(
                self._input[self._offset : self._offset + 1], self._offset, []
            )
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::single_quoted", '"\'"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                index3, elements2 = self._offset, []
                address4 = FAILURE
                index4 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "'":
                    address4 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address4 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::single_quoted", '"\'"'))
                self._offset = index4
                if address4 is FAILURE:
                    address4 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address4 = FAILURE
                if address4 is not FAILURE:
                    elements2.append(address4)
                    address5 = FAILURE
                    if self._offset < self._input_size:
                        address5 = TreeNode(
                            self._input[self._offset : self._offset + 1],
                            self._offset,
                            [],
                        )
                        self._offset = self._offset + 1
                    else:
                        address5 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(
                                ("HeredocLine::single_quoted", "<any char>")
                            )
                    if address5 is not FAILURE:
                        elements2.append(address5)
                    else:
                        elements2 = None
                        self._offset = index3
                else:
                    elements2 = None
                    self._offset = index3
                if elements2 is None:
                    address3 = FAILURE
                else:
                    address3 = TreeNode(
                        self._input[index3 : self._offset], index3, elements2
                    )
                    self._offset = self._offset
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(
                    self._input[index2 : self._offset], index2, elements1
                )
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
                address6 = FAILURE
                chunk2, max2 = None, self._offset + 1
                if max2 <= self._input_size:
                    chunk2 = self._input[self._offset : max2]
                if chunk2 == "'":
                    address6 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address6 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::single_quoted", '"\'"'))
                if address6 is not FAILURE:
                    elements0.append(address6)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["single_quoted"][index0] = (address0, self._offset)
        return address0

    def _read_double_quoted(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["double_quoted"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '"':
            address1 = TreeNode(
                self._input[self._offset : self._offset + 1], self._offset, []
            )
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::double_quoted", "'\"'"))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                index3 = self._offset
                address3 = self._read_escaped_char()
                if address3 is FAILURE:
                    self._offset = index3
                    index4, elements2 = self._offset, []
                    address4 = FAILURE
                    index5 = self._offset
                    chunk1, max1 = None, self._offset + 1
                    if max1 <= self._input_size:
                        chunk1 = self._input[self._offset : max1]
                    if chunk1 == '"':
                        address4 = TreeNode(
                            self._input[self._offset : self._offset + 1],
                            self._offset,
                            [],
                        )
                        self._offset = self._offset + 1
                    else:
                        address4 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(
                                ("HeredocLine::double_quoted", "'\"'")
                            )
                    self._offset = index5
                    if address4 is FAILURE:
                        address4 = TreeNode(
                            self._input[self._offset : self._offset], self._offset, []
                        )
                        self._offset = self._offset
                    else:
                        address4 = FAILURE
                    if address4 is not FAILURE:
                        elements2.append(address4)
                        address5 = FAILURE
                        if self._offset < self._input_size:
                            address5 = TreeNode(
                                self._input[self._offset : self._offset + 1],
                                self._offset,
                                [],
                            )
                            self._offset = self._offset + 1
                        else:
                            address5 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(
                                    ("HeredocLine::double_quoted", "<any char>")
                                )
                        if address5 is not FAILURE:
                            elements2.append(address5)
                        else:
                            elements2 = None
                            self._offset = index4
                    else:
                        elements2 = None
                        self._offset = index4
                    if elements2 is None:
                        address3 = FAILURE
                    else:
                        address3 = TreeNode(
                            self._input[index4 : self._offset], index4, elements2
                        )
                        self._offset = self._offset
                    if address3 is FAILURE:
                        self._offset = index3
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(
                    self._input[index2 : self._offset], index2, elements1
                )
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
                address6 = FAILURE
                chunk2, max2 = None, self._offset + 1
                if max2 <= self._input_size:
                    chunk2 = self._input[self._offset : max2]
                if chunk2 == '"':
                    address6 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address6 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::double_quoted", "'\"'"))
                if address6 is not FAILURE:
                    elements0.append(address6)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["double_quoted"][index0] = (address0, self._offset)
        return address0

    def _read_opaque_subst(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["opaque_subst"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_dollar_paren()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_backtick()
            if address0 is FAILURE:
                self._offset = index1
        self._cache["opaque_subst"][index0] = (address0, self._offset)
        return address0

    def _read_dollar_paren(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["dollar_paren"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 2
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "$(":
            address1 = TreeNode(
                self._input[self._offset : self._offset + 2], self._offset, []
            )
            self._offset = self._offset + 2
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::dollar_paren", '"$("'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_paren_body()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == ")":
                    address3 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::dollar_paren", '")"'))
                if address3 is not FAILURE:
                    elements0.append(address3)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode18(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["dollar_paren"][index0] = (address0, self._offset)
        return address0

    def _read_paren_body(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["paren_body"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2 = self._offset
            address1 = self._read_dollar_paren()
            if address1 is FAILURE:
                self._offset = index2
                address1 = self._read_single_quoted()
                if address1 is FAILURE:
                    self._offset = index2
                    address1 = self._read_double_quoted()
                    if address1 is FAILURE:
                        self._offset = index2
                        index3, elements1 = self._offset, []
                        address2 = FAILURE
                        index4 = self._offset
                        index5 = self._offset
                        chunk0, max0 = None, self._offset + 1
                        if max0 <= self._input_size:
                            chunk0 = self._input[self._offset : max0]
                        if chunk0 == "(":
                            address2 = TreeNode(
                                self._input[self._offset : self._offset + 1],
                                self._offset,
                                [],
                            )
                            self._offset = self._offset + 1
                        else:
                            address2 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(
                                    ("HeredocLine::paren_body", '"("')
                                )
                        if address2 is FAILURE:
                            self._offset = index5
                            chunk1, max1 = None, self._offset + 1
                            if max1 <= self._input_size:
                                chunk1 = self._input[self._offset : max1]
                            if chunk1 == ")":
                                address2 = TreeNode(
                                    self._input[self._offset : self._offset + 1],
                                    self._offset,
                                    [],
                                )
                                self._offset = self._offset + 1
                            else:
                                address2 = FAILURE
                                if self._offset > self._failure:
                                    self._failure = self._offset
                                    self._expected = []
                                if self._offset == self._failure:
                                    self._expected.append(
                                        ("HeredocLine::paren_body", '")"')
                                    )
                            if address2 is FAILURE:
                                self._offset = index5
                        self._offset = index4
                        if address2 is FAILURE:
                            address2 = TreeNode(
                                self._input[self._offset : self._offset],
                                self._offset,
                                [],
                            )
                            self._offset = self._offset
                        else:
                            address2 = FAILURE
                        if address2 is not FAILURE:
                            elements1.append(address2)
                            address3 = FAILURE
                            if self._offset < self._input_size:
                                address3 = TreeNode(
                                    self._input[self._offset : self._offset + 1],
                                    self._offset,
                                    [],
                                )
                                self._offset = self._offset + 1
                            else:
                                address3 = FAILURE
                                if self._offset > self._failure:
                                    self._failure = self._offset
                                    self._expected = []
                                if self._offset == self._failure:
                                    self._expected.append(
                                        ("HeredocLine::paren_body", "<any char>")
                                    )
                            if address3 is not FAILURE:
                                elements1.append(address3)
                            else:
                                elements1 = None
                                self._offset = index3
                        else:
                            elements1 = None
                            self._offset = index3
                        if elements1 is None:
                            address1 = FAILURE
                        else:
                            address1 = TreeNode(
                                self._input[index3 : self._offset], index3, elements1
                            )
                            self._offset = self._offset
                        if address1 is FAILURE:
                            self._offset = index2
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 0:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache["paren_body"][index0] = (address0, self._offset)
        return address0

    def _read_backtick(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["backtick"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "`":
            address1 = TreeNode(
                self._input[self._offset : self._offset + 1], self._offset, []
            )
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::backtick", '"`"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                index3, elements2 = self._offset, []
                address4 = FAILURE
                index4 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "`":
                    address4 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address4 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::backtick", '"`"'))
                self._offset = index4
                if address4 is FAILURE:
                    address4 = TreeNode(
                        self._input[self._offset : self._offset], self._offset, []
                    )
                    self._offset = self._offset
                else:
                    address4 = FAILURE
                if address4 is not FAILURE:
                    elements2.append(address4)
                    address5 = FAILURE
                    if self._offset < self._input_size:
                        address5 = TreeNode(
                            self._input[self._offset : self._offset + 1],
                            self._offset,
                            [],
                        )
                        self._offset = self._offset + 1
                    else:
                        address5 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(
                                ("HeredocLine::backtick", "<any char>")
                            )
                    if address5 is not FAILURE:
                        elements2.append(address5)
                    else:
                        elements2 = None
                        self._offset = index3
                else:
                    elements2 = None
                    self._offset = index3
                if elements2 is None:
                    address3 = FAILURE
                else:
                    address3 = TreeNode(
                        self._input[index3 : self._offset], index3, elements2
                    )
                    self._offset = self._offset
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(
                    self._input[index2 : self._offset], index2, elements1
                )
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
                address6 = FAILURE
                chunk2, max2 = None, self._offset + 1
                if max2 <= self._input_size:
                    chunk2 = self._input[self._offset : max2]
                if chunk2 == "`":
                    address6 = TreeNode(
                        self._input[self._offset : self._offset + 1], self._offset, []
                    )
                    self._offset = self._offset + 1
                else:
                    address6 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(("HeredocLine::backtick", '"`"'))
                if address6 is not FAILURE:
                    elements0.append(address6)
                else:
                    elements0 = None
                    self._offset = index1
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["backtick"][index0] = (address0, self._offset)
        return address0

    def _read_escaped_char(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["escaped_char"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "\\":
            address1 = TreeNode(
                self._input[self._offset : self._offset + 1], self._offset, []
            )
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::escaped_char", '"\\\\"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            if self._offset < self._input_size:
                address2 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::escaped_char", "<any char>"))
            if address2 is not FAILURE:
                elements0.append(address2)
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache["escaped_char"][index0] = (address0, self._offset)
        return address0

    def _read_delimiter(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["delimiter"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_4.search(chunk0):
            address0 = TreeNode(
                self._input[self._offset : self._offset + 1], self._offset, []
            )
            self._offset = self._offset + 1
        else:
            address0 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(("HeredocLine::delimiter", "[ \\t|&;<>()\"'`]"))
        self._cache["delimiter"][index0] = (address0, self._offset)
        return address0

    def _read_spacing(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache["spacing"].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 is not None and Grammar.REGEX_5.search(chunk0):
                address1 = TreeNode(
                    self._input[self._offset : self._offset + 1], self._offset, []
                )
                self._offset = self._offset + 1
            else:
                address1 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(("HeredocLine::spacing", "[ \\t]"))
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 0:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache["spacing"][index0] = (address0, self._offset)
        return address0


class Parser(Grammar):
    def __init__(self, input, actions, types):
        self._input = input
        self._input_size = len(input)
        self._actions = actions
        self._types = types
        self._offset = 0
        self._cache = defaultdict(dict)
        self._failure = 0
        self._expected = []

    def parse(self):
        tree = self._read_line()
        if tree is not FAILURE and self._offset == self._input_size:
            return tree
        if not self._expected:
            self._failure = self._offset
            self._expected.append(("HeredocLine", "<EOF>"))
        raise ParseError(format_error(self._input, self._failure, self._expected))


class ParseError(SyntaxError):
    pass


def parse(input, actions=None, types=None):
    parser = Parser(input, actions, types)
    return parser.parse()


def format_error(input, offset, expected):
    lines = input.split("\n")
    line_no, position = 0, 0

    while position <= offset:
        position += len(lines[line_no]) + 1
        line_no += 1

    line = lines[line_no - 1]
    message = "Line " + str(line_no) + ": expected one of:\n\n"

    for pair in expected:
        message += "    - " + pair[1] + " from " + pair[0] + "\n"

    number = str(line_no)
    while len(number) < 6:
        number = " " + number

    message += "\n" + number + " | " + line + "\n"
    message += " " * (len(line) + 10 + offset - position)
    return message + "^"
