# This file was generated from toolguard/parser/bash_parser.peg
# See https://canopy.jcoglan.com/ for documentation

import re
from collections import defaultdict


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
        self.spacing = elements[2]
        self.compound_command = elements[1]


class TreeNode2(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode2, self).__init__(text, offset, elements)
        self.pipeline = elements[0]


class TreeNode3(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode3, self).__init__(text, offset, elements)
        self.control_op = elements[0]
        self.pipeline = elements[1]


class TreeNode4(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode4, self).__init__(text, offset, elements)
        self.spacing = elements[2]


class TreeNode5(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode5, self).__init__(text, offset, elements)
        self.spacing = elements[2]


class TreeNode6(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode6, self).__init__(text, offset, elements)
        self.spacing = elements[2]


class TreeNode7(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode7, self).__init__(text, offset, elements)
        self.spacing = elements[3]


class TreeNode8(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode8, self).__init__(text, offset, elements)
        self.spacing = elements[0]


class TreeNode9(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode9, self).__init__(text, offset, elements)
        self.spacing = elements[0]


class TreeNode10(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode10, self).__init__(text, offset, elements)
        self.pipeline_element = elements[0]


class TreeNode11(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode11, self).__init__(text, offset, elements)
        self.pipe = elements[0]
        self.pipeline_element = elements[1]


class TreeNode12(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode12, self).__init__(text, offset, elements)
        self.spacing = elements[3]


class TreeNode13(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode13, self).__init__(text, offset, elements)
        self.spacing = elements[3]
        self.compound_command = elements[2]


class TreeNode14(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode14, self).__init__(text, offset, elements)
        self.spacing = elements[3]
        self.compound_command = elements[2]


class TreeNode15(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode15, self).__init__(text, offset, elements)
        self.word = elements[1]
        self.spacing = elements[2]


class TreeNode16(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode16, self).__init__(text, offset, elements)
        self.spacing = elements[5]
        self.file_path = elements[4]


class TreeNode17(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode17, self).__init__(text, offset, elements)
        self.spacing = elements[4]
        self.heredoc_delimiter = elements[3]


class TreeNode18(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode18, self).__init__(text, offset, elements)
        self.spacing = elements[4]
        self.file_path = elements[3]


class TreeNode19(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode19, self).__init__(text, offset, elements)
        self.spacing = elements[4]
        self.file_path = elements[3]


class TreeNode20(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode20, self).__init__(text, offset, elements)
        self.spacing = elements[4]
        self.file_path = elements[3]


class TreeNode21(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode21, self).__init__(text, offset, elements)
        self.spacing = elements[1]


class TreeNode22(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode22, self).__init__(text, offset, elements)
        self.fd_num = elements[2]
        self.spacing = elements[3]


class TreeNode23(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode23, self).__init__(text, offset, elements)
        self.spacing = elements[5]
        self.compound_command = elements[2]


class TreeNode24(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode24, self).__init__(text, offset, elements)
        self.spacing = elements[5]
        self.compound_command = elements[2]


class TreeNode25(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode25, self).__init__(text, offset, elements)
        self.path_start = elements[0]


class TreeNode26(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode26, self).__init__(text, offset, elements)
        self.single_content = elements[1]


class TreeNode27(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode27, self).__init__(text, offset, elements)
        self.double_content = elements[1]


class TreeNode28(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode28, self).__init__(text, offset, elements)
        self.dollar_content = elements[1]


class TreeNode29(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode29, self).__init__(text, offset, elements)
        self.identifier = elements[1]


class TreeNode30(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode30, self).__init__(text, offset, elements)
        self.identifier = elements[1]


class TreeNode31(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode31, self).__init__(text, offset, elements)
        self.special_var = elements[1]


FAILURE = object()


class Grammar(object):
    REGEX_1 = re.compile('^[a-zA-Z_]')
    REGEX_2 = re.compile('^[a-zA-Z0-9_]')
    REGEX_3 = re.compile('^[\\n\\r]')
    REGEX_4 = re.compile('^[0-9]')
    REGEX_5 = re.compile('^[a-zA-Z_]')
    REGEX_6 = re.compile('^[a-zA-Z0-9_./-]')
    REGEX_7 = re.compile('^[a-zA-Z_]')
    REGEX_8 = re.compile('^[a-zA-Z0-9_]')
    REGEX_9 = re.compile('^[-+=?]')
    REGEX_10 = re.compile('^[^}]')
    REGEX_11 = re.compile('^[?$!#@*0-9-]')
    REGEX_12 = re.compile('^[a-zA-Z0-9_]')
    REGEX_13 = re.compile('^[ \\t\\n\\r|&;<>(){}$`"\']')
    REGEX_14 = re.compile('^[ \\t]')

    def _read_command_line(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['command_line'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_spacing()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_compound_command()
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
            address0 = TreeNode1(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['command_line'][index0] = (address0, self._offset)
        return address0

    def _read_compound_command(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['compound_command'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_pipeline()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                index3, elements2 = self._offset, []
                address4 = FAILURE
                address4 = self._read_control_op()
                if address4 is not FAILURE:
                    elements2.append(address4)
                    address5 = FAILURE
                    address5 = self._read_pipeline()
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
                    address3 = TreeNode3(self._input[index3 : self._offset], index3, elements2)
                    self._offset = self._offset
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(self._input[index2 : self._offset], index2, elements1)
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
                address6 = FAILURE
                index4 = self._offset
                index5 = self._offset
                address6 = self._read_trailing_background()
                if address6 is FAILURE:
                    self._offset = index5
                    address6 = self._read_trailing_semicolon()
                    if address6 is FAILURE:
                        self._offset = index5
                if address6 is FAILURE:
                    address6 = TreeNode(self._input[index4:index4], index4, [])
                    self._offset = index4
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
            address0 = TreeNode2(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['compound_command'][index0] = (address0, self._offset)
        return address0

    def _read_control_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['control_op'].get(index0)
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
                address0 = self._read_semicolon()
                if address0 is FAILURE:
                    self._offset = index1
                    address0 = self._read_background()
                    if address0 is FAILURE:
                        self._offset = index1
        self._cache['control_op'][index0] = (address0, self._offset)
        return address0

    def _read_and_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['and_op'].get(index0)
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
            if chunk0 == '&&':
                address2 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::and_op', '"&&"'))
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
        self._cache['and_op'][index0] = (address0, self._offset)
        return address0

    def _read_or_op(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['or_op'].get(index0)
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
            if chunk0 == '||':
                address2 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::or_op', '"||"'))
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
            address0 = TreeNode5(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['or_op'][index0] = (address0, self._offset)
        return address0

    def _read_semicolon(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['semicolon'].get(index0)
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
            if chunk0 == ';':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::semicolon', '";"'))
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
            address0 = TreeNode6(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['semicolon'][index0] = (address0, self._offset)
        return address0

    def _read_background(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['background'].get(index0)
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
            if chunk0 == '&':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::background', '"&"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == '&':
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::background', '"&"'))
                self._offset = index2
                if address3 is FAILURE:
                    address3 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
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
            address0 = TreeNode7(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['background'][index0] = (address0, self._offset)
        return address0

    def _read_trailing_background(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['trailing_background'].get(index0)
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
            if chunk0 == '&':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::trailing_background', '"&"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == '&':
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::trailing_background', '"&"'))
                self._offset = index2
                if address3 is FAILURE:
                    address3 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                    self._offset = self._offset
                else:
                    address3 = FAILURE
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    index3 = self._offset
                    address4 = self._read_spacing()
                    if address4 is FAILURE:
                        address4 = TreeNode(self._input[index3:index3], index3, [])
                        self._offset = index3
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
            address0 = TreeNode8(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['trailing_background'][index0] = (address0, self._offset)
        return address0

    def _read_trailing_semicolon(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['trailing_semicolon'].get(index0)
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
            if chunk0 == ';':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::trailing_semicolon', '";"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                address3 = self._read_spacing()
                if address3 is FAILURE:
                    address3 = TreeNode(self._input[index2:index2], index2, [])
                    self._offset = index2
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
            address0 = TreeNode9(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['trailing_semicolon'][index0] = (address0, self._offset)
        return address0

    def _read_pipeline(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['pipeline'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_pipeline_element()
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
                    address5 = self._read_pipeline_element()
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
                    address3 = TreeNode11(self._input[index3 : self._offset], index3, elements2)
                    self._offset = self._offset
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(self._input[index2 : self._offset], index2, elements1)
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
            address0 = TreeNode10(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['pipeline'][index0] = (address0, self._offset)
        return address0

    def _read_pipe(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['pipe'].get(index0)
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
            if chunk0 == '|':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::pipe', '"|"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == '|':
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::pipe', '"|"'))
                self._offset = index2
                if address3 is FAILURE:
                    address3 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
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
            address0 = TreeNode12(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['pipe'][index0] = (address0, self._offset)
        return address0

    def _read_pipeline_element(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['pipeline_element'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_subshell()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_brace_group()
            if address0 is FAILURE:
                self._offset = index1
                address0 = self._read_simple_command()
                if address0 is FAILURE:
                    self._offset = index1
        self._cache['pipeline_element'][index0] = (address0, self._offset)
        return address0

    def _read_subshell(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['subshell'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '(':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::subshell', '"("'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_spacing()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_compound_command()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        chunk1, max1 = None, self._offset + 1
                        if max1 <= self._input_size:
                            chunk1 = self._input[self._offset : max1]
                        if chunk1 == ')':
                            address5 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address5 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::subshell', '")"'))
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
        self._cache['subshell'][index0] = (address0, self._offset)
        return address0

    def _read_brace_group(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['brace_group'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '{':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::brace_group', '"{"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_spacing()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_compound_command()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        chunk1, max1 = None, self._offset + 1
                        if max1 <= self._input_size:
                            chunk1 = self._input[self._offset : max1]
                        if chunk1 == '}':
                            address5 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address5 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::brace_group', '"}"'))
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
            address0 = TreeNode14(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['brace_group'][index0] = (address0, self._offset)
        return address0

    def _read_simple_command(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['simple_command'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2 = self._offset
            address1 = self._read_redirection()
            if address1 is FAILURE:
                self._offset = index2
                address1 = self._read_cmd_substitution()
                if address1 is FAILURE:
                    self._offset = index2
                    address1 = self._read_command_word()
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
        self._cache['simple_command'][index0] = (address0, self._offset)
        return address0

    def _read_command_word(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['command_word'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        index2 = self._offset
        address1 = self._read_reserved_word()
        self._offset = index2
        if address1 is FAILURE:
            address1 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
            self._offset = self._offset
        else:
            address1 = FAILURE
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_word()
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
            address0 = TreeNode15(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['command_word'][index0] = (address0, self._offset)
        return address0

    def _read_redirection(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['redirection'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_append_redirect()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_output_redirect()
            if address0 is FAILURE:
                self._offset = index1
                address0 = self._read_heredoc()
                if address0 is FAILURE:
                    self._offset = index1
                    address0 = self._read_input_redirect()
                    if address0 is FAILURE:
                        self._offset = index1
                        address0 = self._read_stderr_redirect()
                        if address0 is FAILURE:
                            self._offset = index1
                            address0 = self._read_stderr_to_stdout()
                            if address0 is FAILURE:
                                self._offset = index1
                                address0 = self._read_fd_redirect()
                                if address0 is FAILURE:
                                    self._offset = index1
        self._cache['redirection'][index0] = (address0, self._offset)
        return address0

    def _read_output_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['output_redirect'].get(index0)
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
            if chunk0 == '>':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::output_redirect', '">"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index3 = self._offset
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == '>':
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::output_redirect', '">"'))
                self._offset = index3
                if address3 is FAILURE:
                    address3 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
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
                        address5 = self._read_file_path()
                        if address5 is not FAILURE:
                            elements0.append(address5)
                            address6 = FAILURE
                            address6 = self._read_spacing()
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
        self._cache['output_redirect'][index0] = (address0, self._offset)
        return address0

    def _read_heredoc(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['heredoc'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 2
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '<<':
            address1 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
            self._offset = self._offset + 2
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::heredoc', '"<<"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2 = self._offset
            chunk1, max1 = None, self._offset + 1
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 == '-':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::heredoc', '"-"'))
            if address2 is FAILURE:
                address2 = TreeNode(self._input[index2:index2], index2, [])
                self._offset = index2
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_heredoc_delimiter()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        address5 = self._read_spacing()
                        if address5 is not FAILURE:
                            elements0.append(address5)
                            address6 = FAILURE
                            index3 = self._offset
                            address6 = self._read_heredoc_content()
                            if address6 is FAILURE:
                                address6 = TreeNode(self._input[index3:index3], index3, [])
                                self._offset = index3
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
        self._cache['heredoc'][index0] = (address0, self._offset)
        return address0

    def _read_heredoc_delimiter(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['heredoc_delimiter'].get(index0)
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
                address0 = self._read_unquoted_heredoc_word()
                if address0 is FAILURE:
                    self._offset = index1
        self._cache['heredoc_delimiter'][index0] = (address0, self._offset)
        return address0

    def _read_unquoted_heredoc_word(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['unquoted_heredoc_word'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_1.search(chunk0):
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::unquoted_heredoc_word', '[a-zA-Z_]'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 is not None and Grammar.REGEX_2.search(chunk1):
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::unquoted_heredoc_word', '[a-zA-Z0-9_]'))
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(self._input[index2 : self._offset], index2, elements1)
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
        self._cache['unquoted_heredoc_word'][index0] = (address0, self._offset)
        return address0

    def _read_heredoc_content(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['heredoc_content'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2, elements1 = self._offset, []
            address2 = FAILURE
            index3 = self._offset
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 is not None and Grammar.REGEX_3.search(chunk0):
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::heredoc_content', '[\\n\\r]'))
            self._offset = index3
            if address2 is FAILURE:
                address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements1.append(address2)
                address3 = FAILURE
                if self._offset < self._input_size:
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::heredoc_content', '<any char>'))
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    elements1 = None
                    self._offset = index2
            else:
                elements1 = None
                self._offset = index2
            if elements1 is None:
                address1 = FAILURE
            else:
                address1 = TreeNode(self._input[index2 : self._offset], index2, elements1)
                self._offset = self._offset
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 0:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache['heredoc_content'][index0] = (address0, self._offset)
        return address0

    def _read_append_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['append_redirect'].get(index0)
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
            if chunk0 == '>>':
                address2 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::append_redirect', '">>"'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_file_path()
                    if address4 is not FAILURE:
                        elements0.append(address4)
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
        self._cache['append_redirect'][index0] = (address0, self._offset)
        return address0

    def _read_input_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['input_redirect'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '<':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::input_redirect', '"<"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2 = self._offset
            chunk1, max1 = None, self._offset + 1
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 == '<':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::input_redirect', '"<"'))
            self._offset = index2
            if address2 is FAILURE:
                address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_file_path()
                    if address4 is not FAILURE:
                        elements0.append(address4)
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
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode19(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['input_redirect'][index0] = (address0, self._offset)
        return address0

    def _read_stderr_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['stderr_redirect'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 2
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '2>':
            address1 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
            self._offset = self._offset + 2
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::stderr_redirect', '"2>"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2 = self._offset
            chunk1, max1 = None, self._offset + 1
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 == '>':
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::stderr_redirect', '">"'))
            self._offset = index2
            if address2 is FAILURE:
                address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_spacing()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_file_path()
                    if address4 is not FAILURE:
                        elements0.append(address4)
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
            else:
                elements0 = None
                self._offset = index1
        else:
            elements0 = None
            self._offset = index1
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode20(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['stderr_redirect'][index0] = (address0, self._offset)
        return address0

    def _read_stderr_to_stdout(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['stderr_to_stdout'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 4
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '2>&1':
            address1 = TreeNode(self._input[self._offset : self._offset + 4], self._offset, [])
            self._offset = self._offset + 4
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::stderr_to_stdout', '"2>&1"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_spacing()
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
            address0 = TreeNode21(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['stderr_to_stdout'][index0] = (address0, self._offset)
        return address0

    def _read_fd_redirect(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['fd_redirect'].get(index0)
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
            if chunk0 == '>&':
                address2 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                self._offset = self._offset + 2
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::fd_redirect', '">&"'))
            if address2 is FAILURE:
                self._offset = index2
                chunk1, max1 = None, self._offset + 2
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == '<&':
                    address2 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                    self._offset = self._offset + 2
                else:
                    address2 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::fd_redirect', '"<&"'))
                if address2 is FAILURE:
                    self._offset = index2
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_fd_num()
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
            address0 = TreeNode22(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['fd_redirect'][index0] = (address0, self._offset)
        return address0

    def _read_fd_num(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['fd_num'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 is not None and Grammar.REGEX_4.search(chunk0):
                address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address1 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::fd_num', '[0-9]'))
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 1:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache['fd_num'][index0] = (address0, self._offset)
        return address0

    def _read_cmd_substitution(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['cmd_substitution'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_dollar_paren_sub()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_backtick_sub()
            if address0 is FAILURE:
                self._offset = index1
        self._cache['cmd_substitution'][index0] = (address0, self._offset)
        return address0

    def _read_dollar_paren_sub(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['dollar_paren_sub'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 2
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '$(':
            address1 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
            self._offset = self._offset + 2
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::dollar_paren_sub', '"$("'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_spacing()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_compound_command()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        chunk1, max1 = None, self._offset + 1
                        if max1 <= self._input_size:
                            chunk1 = self._input[self._offset : max1]
                        if chunk1 == ')':
                            address5 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address5 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::dollar_paren_sub', '")"'))
                        if address5 is not FAILURE:
                            elements0.append(address5)
                            address6 = FAILURE
                            address6 = self._read_spacing()
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
            address0 = TreeNode23(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['dollar_paren_sub'][index0] = (address0, self._offset)
        return address0

    def _read_backtick_sub(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['backtick_sub'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '`':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::backtick_sub', '"`"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_spacing()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                address3 = self._read_compound_command()
                if address3 is not FAILURE:
                    elements0.append(address3)
                    address4 = FAILURE
                    address4 = self._read_spacing()
                    if address4 is not FAILURE:
                        elements0.append(address4)
                        address5 = FAILURE
                        chunk1, max1 = None, self._offset + 1
                        if max1 <= self._input_size:
                            chunk1 = self._input[self._offset : max1]
                        if chunk1 == '`':
                            address5 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address5 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::backtick_sub', '"`"'))
                        if address5 is not FAILURE:
                            elements0.append(address5)
                            address6 = FAILURE
                            address6 = self._read_spacing()
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
            address0 = TreeNode24(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['backtick_sub'][index0] = (address0, self._offset)
        return address0

    def _read_file_path(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['file_path'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_quoted_path()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_unquoted_path()
            if address0 is FAILURE:
                self._offset = index1
        self._cache['file_path'][index0] = (address0, self._offset)
        return address0

    def _read_quoted_path(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['quoted_path'].get(index0)
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
        self._cache['quoted_path'][index0] = (address0, self._offset)
        return address0

    def _read_unquoted_path(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['unquoted_path'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        address1 = self._read_path_start()
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                address3 = self._read_path_char()
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(self._input[index2 : self._offset], index2, elements1)
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
            address0 = TreeNode25(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['unquoted_path'][index0] = (address0, self._offset)
        return address0

    def _read_path_start(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['path_start'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '/':
            address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address0 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::path_start', '"/"'))
        if address0 is FAILURE:
            self._offset = index1
            chunk1, max1 = None, self._offset + 1
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 == '~':
                address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address0 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::path_start', '"~"'))
            if address0 is FAILURE:
                self._offset = index1
                chunk2, max2 = None, self._offset + 1
                if max2 <= self._input_size:
                    chunk2 = self._input[self._offset : max2]
                if chunk2 == '.':
                    address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address0 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::path_start', '"."'))
                if address0 is FAILURE:
                    self._offset = index1
                    chunk3, max3 = None, self._offset + 1
                    if max3 <= self._input_size:
                        chunk3 = self._input[self._offset : max3]
                    if chunk3 is not None and Grammar.REGEX_5.search(chunk3):
                        address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                        self._offset = self._offset + 1
                    else:
                        address0 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(('BashParser::path_start', '[a-zA-Z_]'))
                    if address0 is FAILURE:
                        self._offset = index1
        self._cache['path_start'][index0] = (address0, self._offset)
        return address0

    def _read_path_char(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['path_char'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_6.search(chunk0):
            address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address0 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::path_char', '[a-zA-Z0-9_./-]'))
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_escaped_char()
            if address0 is FAILURE:
                self._offset = index1
        self._cache['path_char'][index0] = (address0, self._offset)
        return address0

    def _read_escaped_char(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['escaped_char'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '\\':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::escaped_char', '"\\\\"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            if self._offset < self._input_size:
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::escaped_char', '<any char>'))
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
        self._cache['escaped_char'][index0] = (address0, self._offset)
        return address0

    def _read_word(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['word'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        address0 = self._read_quoted_string()
        if address0 is FAILURE:
            self._offset = index1
            address0 = self._read_unquoted_word()
            if address0 is FAILURE:
                self._offset = index1
        self._cache['word'][index0] = (address0, self._offset)
        return address0

    def _read_quoted_string(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['quoted_string'].get(index0)
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
                address0 = self._read_dollar_quoted()
                if address0 is FAILURE:
                    self._offset = index1
        self._cache['quoted_string'][index0] = (address0, self._offset)
        return address0

    def _read_single_quoted(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['single_quoted'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "'":
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::single_quoted', '"\'"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_single_content()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "'":
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::single_quoted', '"\'"'))
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
            address0 = TreeNode26(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['single_quoted'][index0] = (address0, self._offset)
        return address0

    def _read_single_content(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['single_content'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2, elements1 = self._offset, []
            address2 = FAILURE
            index3 = self._offset
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 == "'":
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::single_content', '"\'"'))
            self._offset = index3
            if address2 is FAILURE:
                address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                self._offset = self._offset
            else:
                address2 = FAILURE
            if address2 is not FAILURE:
                elements1.append(address2)
                address3 = FAILURE
                if self._offset < self._input_size:
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::single_content', '<any char>'))
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    elements1 = None
                    self._offset = index2
            else:
                elements1 = None
                self._offset = index2
            if elements1 is None:
                address1 = FAILURE
            else:
                address1 = TreeNode(self._input[index2 : self._offset], index2, elements1)
                self._offset = self._offset
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 0:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache['single_content'][index0] = (address0, self._offset)
        return address0

    def _read_double_quoted(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['double_quoted'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '"':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::double_quoted', "'\"'"))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_double_content()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == '"':
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::double_quoted', "'\"'"))
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
            address0 = TreeNode27(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['double_quoted'][index0] = (address0, self._offset)
        return address0

    def _read_double_content(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['double_content'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2 = self._offset
            address1 = self._read_escaped_char()
            if address1 is FAILURE:
                self._offset = index2
                address1 = self._read_var_ref()
                if address1 is FAILURE:
                    self._offset = index2
                    address1 = self._read_cmd_substitution()
                    if address1 is FAILURE:
                        self._offset = index2
                        index3, elements1 = self._offset, []
                        address2 = FAILURE
                        index4 = self._offset
                        chunk0, max0 = None, self._offset + 1
                        if max0 <= self._input_size:
                            chunk0 = self._input[self._offset : max0]
                        if chunk0 == '"':
                            address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address2 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::double_content', "'\"'"))
                        self._offset = index4
                        if address2 is FAILURE:
                            address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                            self._offset = self._offset
                        else:
                            address2 = FAILURE
                        if address2 is not FAILURE:
                            elements1.append(address2)
                            address3 = FAILURE
                            if self._offset < self._input_size:
                                address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                                self._offset = self._offset + 1
                            else:
                                address3 = FAILURE
                                if self._offset > self._failure:
                                    self._failure = self._offset
                                    self._expected = []
                                if self._offset == self._failure:
                                    self._expected.append(('BashParser::double_content', '<any char>'))
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
                            address1 = TreeNode(self._input[index3 : self._offset], index3, elements1)
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
        self._cache['double_content'][index0] = (address0, self._offset)
        return address0

    def _read_dollar_quoted(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['dollar_quoted'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 2
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == "$'":
            address1 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
            self._offset = self._offset + 2
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::dollar_quoted', '"$\'"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_dollar_content()
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 == "'":
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::dollar_quoted', '"\'"'))
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
            address0 = TreeNode28(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['dollar_quoted'][index0] = (address0, self._offset)
        return address0

    def _read_dollar_content(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['dollar_content'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2 = self._offset
            address1 = self._read_escaped_char()
            if address1 is FAILURE:
                self._offset = index2
                index3, elements1 = self._offset, []
                address2 = FAILURE
                index4 = self._offset
                chunk0, max0 = None, self._offset + 1
                if max0 <= self._input_size:
                    chunk0 = self._input[self._offset : max0]
                if chunk0 == "'":
                    address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address2 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::dollar_content', '"\'"'))
                self._offset = index4
                if address2 is FAILURE:
                    address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                    self._offset = self._offset
                else:
                    address2 = FAILURE
                if address2 is not FAILURE:
                    elements1.append(address2)
                    address3 = FAILURE
                    if self._offset < self._input_size:
                        address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                        self._offset = self._offset + 1
                    else:
                        address3 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(('BashParser::dollar_content', '<any char>'))
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
                    address1 = TreeNode(self._input[index3 : self._offset], index3, elements1)
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
        self._cache['dollar_content'][index0] = (address0, self._offset)
        return address0

    def _read_unquoted_word(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['unquoted_word'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            index2 = self._offset
            address1 = self._read_escaped_char()
            if address1 is FAILURE:
                self._offset = index2
                address1 = self._read_var_ref()
                if address1 is FAILURE:
                    self._offset = index2
                    index3, elements1 = self._offset, []
                    address2 = FAILURE
                    index4 = self._offset
                    address2 = self._read_delimiter()
                    self._offset = index4
                    if address2 is FAILURE:
                        address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
                        self._offset = self._offset
                    else:
                        address2 = FAILURE
                    if address2 is not FAILURE:
                        elements1.append(address2)
                        address3 = FAILURE
                        if self._offset < self._input_size:
                            address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address3 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::unquoted_word', '<any char>'))
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
                        address1 = TreeNode(self._input[index3 : self._offset], index3, elements1)
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
        self._cache['unquoted_word'][index0] = (address0, self._offset)
        return address0

    def _read_var_ref(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['var_ref'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1 = self._offset
        index2, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == '$':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::var_ref', '"$"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            address2 = self._read_identifier()
            if address2 is not FAILURE:
                elements0.append(address2)
            else:
                elements0 = None
                self._offset = index2
        else:
            elements0 = None
            self._offset = index2
        if elements0 is None:
            address0 = FAILURE
        else:
            address0 = TreeNode29(self._input[index2 : self._offset], index2, elements0)
            self._offset = self._offset
        if address0 is FAILURE:
            self._offset = index1
            index3, elements1 = self._offset, []
            address3 = FAILURE
            chunk1, max1 = None, self._offset + 2
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 == '${':
                address3 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                self._offset = self._offset + 2
            else:
                address3 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::var_ref', '"${"'))
            if address3 is not FAILURE:
                elements1.append(address3)
                address4 = FAILURE
                address4 = self._read_identifier()
                if address4 is not FAILURE:
                    elements1.append(address4)
                    address5 = FAILURE
                    index4 = self._offset
                    address5 = self._read_var_modifier()
                    if address5 is FAILURE:
                        address5 = TreeNode(self._input[index4:index4], index4, [])
                        self._offset = index4
                    if address5 is not FAILURE:
                        elements1.append(address5)
                        address6 = FAILURE
                        chunk2, max2 = None, self._offset + 1
                        if max2 <= self._input_size:
                            chunk2 = self._input[self._offset : max2]
                        if chunk2 == '}':
                            address6 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                            self._offset = self._offset + 1
                        else:
                            address6 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::var_ref', '"}"'))
                        if address6 is not FAILURE:
                            elements1.append(address6)
                        else:
                            elements1 = None
                            self._offset = index3
                    else:
                        elements1 = None
                        self._offset = index3
                else:
                    elements1 = None
                    self._offset = index3
            else:
                elements1 = None
                self._offset = index3
            if elements1 is None:
                address0 = FAILURE
            else:
                address0 = TreeNode30(self._input[index3 : self._offset], index3, elements1)
                self._offset = self._offset
            if address0 is FAILURE:
                self._offset = index1
                index5, elements2 = self._offset, []
                address7 = FAILURE
                chunk3, max3 = None, self._offset + 1
                if max3 <= self._input_size:
                    chunk3 = self._input[self._offset : max3]
                if chunk3 == '$':
                    address7 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address7 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::var_ref', '"$"'))
                if address7 is not FAILURE:
                    elements2.append(address7)
                    address8 = FAILURE
                    address8 = self._read_special_var()
                    if address8 is not FAILURE:
                        elements2.append(address8)
                    else:
                        elements2 = None
                        self._offset = index5
                else:
                    elements2 = None
                    self._offset = index5
                if elements2 is None:
                    address0 = FAILURE
                else:
                    address0 = TreeNode31(self._input[index5 : self._offset], index5, elements2)
                    self._offset = self._offset
                if address0 is FAILURE:
                    self._offset = index1
        self._cache['var_ref'][index0] = (address0, self._offset)
        return address0

    def _read_identifier(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['identifier'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_7.search(chunk0):
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::identifier', '[a-zA-Z_]'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index2, elements1, address3 = self._offset, [], None
            while True:
                chunk1, max1 = None, self._offset + 1
                if max1 <= self._input_size:
                    chunk1 = self._input[self._offset : max1]
                if chunk1 is not None and Grammar.REGEX_8.search(chunk1):
                    address3 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                    self._offset = self._offset + 1
                else:
                    address3 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::identifier', '[a-zA-Z0-9_]'))
                if address3 is not FAILURE:
                    elements1.append(address3)
                else:
                    break
            if len(elements1) >= 0:
                address2 = TreeNode(self._input[index2 : self._offset], index2, elements1)
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
        self._cache['identifier'][index0] = (address0, self._offset)
        return address0

    def _read_var_modifier(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['var_modifier'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == ':':
            address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::var_modifier', '":"'))
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            chunk1, max1 = None, self._offset + 1
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 is not None and Grammar.REGEX_9.search(chunk1):
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::var_modifier', '[-+=?]'))
            if address2 is not FAILURE:
                elements0.append(address2)
                address3 = FAILURE
                index2, elements1, address4 = self._offset, [], None
                while True:
                    chunk2, max2 = None, self._offset + 1
                    if max2 <= self._input_size:
                        chunk2 = self._input[self._offset : max2]
                    if chunk2 is not None and Grammar.REGEX_10.search(chunk2):
                        address4 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                        self._offset = self._offset + 1
                    else:
                        address4 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(('BashParser::var_modifier', '[^}]'))
                    if address4 is not FAILURE:
                        elements1.append(address4)
                    else:
                        break
                if len(elements1) >= 0:
                    address3 = TreeNode(self._input[index2 : self._offset], index2, elements1)
                    self._offset = self._offset
                else:
                    address3 = FAILURE
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
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        self._cache['var_modifier'][index0] = (address0, self._offset)
        return address0

    def _read_special_var(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['special_var'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_11.search(chunk0):
            address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address0 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::special_var', '[?$!#@*0-9-]'))
        self._cache['special_var'][index0] = (address0, self._offset)
        return address0

    def _read_reserved_word(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['reserved_word'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0 = self._offset, []
        address1 = FAILURE
        index2 = self._offset
        chunk0, max0 = None, self._offset + 2
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 == 'if':
            address1 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
            self._offset = self._offset + 2
        else:
            address1 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::reserved_word', '"if"'))
        if address1 is FAILURE:
            self._offset = index2
            chunk1, max1 = None, self._offset + 4
            if max1 <= self._input_size:
                chunk1 = self._input[self._offset : max1]
            if chunk1 == 'then':
                address1 = TreeNode(self._input[self._offset : self._offset + 4], self._offset, [])
                self._offset = self._offset + 4
            else:
                address1 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::reserved_word', '"then"'))
            if address1 is FAILURE:
                self._offset = index2
                chunk2, max2 = None, self._offset + 4
                if max2 <= self._input_size:
                    chunk2 = self._input[self._offset : max2]
                if chunk2 == 'else':
                    address1 = TreeNode(self._input[self._offset : self._offset + 4], self._offset, [])
                    self._offset = self._offset + 4
                else:
                    address1 = FAILURE
                    if self._offset > self._failure:
                        self._failure = self._offset
                        self._expected = []
                    if self._offset == self._failure:
                        self._expected.append(('BashParser::reserved_word', '"else"'))
                if address1 is FAILURE:
                    self._offset = index2
                    chunk3, max3 = None, self._offset + 4
                    if max3 <= self._input_size:
                        chunk3 = self._input[self._offset : max3]
                    if chunk3 == 'elif':
                        address1 = TreeNode(self._input[self._offset : self._offset + 4], self._offset, [])
                        self._offset = self._offset + 4
                    else:
                        address1 = FAILURE
                        if self._offset > self._failure:
                            self._failure = self._offset
                            self._expected = []
                        if self._offset == self._failure:
                            self._expected.append(('BashParser::reserved_word', '"elif"'))
                    if address1 is FAILURE:
                        self._offset = index2
                        chunk4, max4 = None, self._offset + 2
                        if max4 <= self._input_size:
                            chunk4 = self._input[self._offset : max4]
                        if chunk4 == 'fi':
                            address1 = TreeNode(self._input[self._offset : self._offset + 2], self._offset, [])
                            self._offset = self._offset + 2
                        else:
                            address1 = FAILURE
                            if self._offset > self._failure:
                                self._failure = self._offset
                                self._expected = []
                            if self._offset == self._failure:
                                self._expected.append(('BashParser::reserved_word', '"fi"'))
                        if address1 is FAILURE:
                            self._offset = index2
                            chunk5, max5 = None, self._offset + 4
                            if max5 <= self._input_size:
                                chunk5 = self._input[self._offset : max5]
                            if chunk5 == 'case':
                                address1 = TreeNode(self._input[self._offset : self._offset + 4], self._offset, [])
                                self._offset = self._offset + 4
                            else:
                                address1 = FAILURE
                                if self._offset > self._failure:
                                    self._failure = self._offset
                                    self._expected = []
                                if self._offset == self._failure:
                                    self._expected.append(('BashParser::reserved_word', '"case"'))
                            if address1 is FAILURE:
                                self._offset = index2
                                chunk6, max6 = None, self._offset + 4
                                if max6 <= self._input_size:
                                    chunk6 = self._input[self._offset : max6]
                                if chunk6 == 'esac':
                                    address1 = TreeNode(self._input[self._offset : self._offset + 4], self._offset, [])
                                    self._offset = self._offset + 4
                                else:
                                    address1 = FAILURE
                                    if self._offset > self._failure:
                                        self._failure = self._offset
                                        self._expected = []
                                    if self._offset == self._failure:
                                        self._expected.append(('BashParser::reserved_word', '"esac"'))
                                if address1 is FAILURE:
                                    self._offset = index2
                                    chunk7, max7 = None, self._offset + 3
                                    if max7 <= self._input_size:
                                        chunk7 = self._input[self._offset : max7]
                                    if chunk7 == 'for':
                                        address1 = TreeNode(
                                            self._input[self._offset : self._offset + 3], self._offset, []
                                        )
                                        self._offset = self._offset + 3
                                    else:
                                        address1 = FAILURE
                                        if self._offset > self._failure:
                                            self._failure = self._offset
                                            self._expected = []
                                        if self._offset == self._failure:
                                            self._expected.append(('BashParser::reserved_word', '"for"'))
                                    if address1 is FAILURE:
                                        self._offset = index2
                                        chunk8, max8 = None, self._offset + 5
                                        if max8 <= self._input_size:
                                            chunk8 = self._input[self._offset : max8]
                                        if chunk8 == 'while':
                                            address1 = TreeNode(
                                                self._input[self._offset : self._offset + 5], self._offset, []
                                            )
                                            self._offset = self._offset + 5
                                        else:
                                            address1 = FAILURE
                                            if self._offset > self._failure:
                                                self._failure = self._offset
                                                self._expected = []
                                            if self._offset == self._failure:
                                                self._expected.append(('BashParser::reserved_word', '"while"'))
                                        if address1 is FAILURE:
                                            self._offset = index2
                                            chunk9, max9 = None, self._offset + 5
                                            if max9 <= self._input_size:
                                                chunk9 = self._input[self._offset : max9]
                                            if chunk9 == 'until':
                                                address1 = TreeNode(
                                                    self._input[self._offset : self._offset + 5], self._offset, []
                                                )
                                                self._offset = self._offset + 5
                                            else:
                                                address1 = FAILURE
                                                if self._offset > self._failure:
                                                    self._failure = self._offset
                                                    self._expected = []
                                                if self._offset == self._failure:
                                                    self._expected.append(('BashParser::reserved_word', '"until"'))
                                            if address1 is FAILURE:
                                                self._offset = index2
                                                chunk10, max10 = None, self._offset + 2
                                                if max10 <= self._input_size:
                                                    chunk10 = self._input[self._offset : max10]
                                                if chunk10 == 'do':
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
                                                        self._expected.append(('BashParser::reserved_word', '"do"'))
                                                if address1 is FAILURE:
                                                    self._offset = index2
                                                    chunk11, max11 = None, self._offset + 4
                                                    if max11 <= self._input_size:
                                                        chunk11 = self._input[self._offset : max11]
                                                    if chunk11 == 'done':
                                                        address1 = TreeNode(
                                                            self._input[self._offset : self._offset + 4],
                                                            self._offset,
                                                            [],
                                                        )
                                                        self._offset = self._offset + 4
                                                    else:
                                                        address1 = FAILURE
                                                        if self._offset > self._failure:
                                                            self._failure = self._offset
                                                            self._expected = []
                                                        if self._offset == self._failure:
                                                            self._expected.append(
                                                                ('BashParser::reserved_word', '"done"')
                                                            )
                                                    if address1 is FAILURE:
                                                        self._offset = index2
                                                        chunk12, max12 = None, self._offset + 2
                                                        if max12 <= self._input_size:
                                                            chunk12 = self._input[self._offset : max12]
                                                        if chunk12 == 'in':
                                                            address1 = TreeNode(
                                                                self._input[self._offset : self._offset + 2],
                                                                self._offset,
                                                                [],
                                                            )
                                                            self._offset = self._offset + 2
                                                        else:
                                                            address1 = FAILURE
                                                            if self._offset > self._failure:
                                                                self._failure = self._offset
                                                                self._expected = []
                                                            if self._offset == self._failure:
                                                                self._expected.append(
                                                                    ('BashParser::reserved_word', '"in"')
                                                                )
                                                        if address1 is FAILURE:
                                                            self._offset = index2
                                                            chunk13, max13 = None, self._offset + 8
                                                            if max13 <= self._input_size:
                                                                chunk13 = self._input[self._offset : max13]
                                                            if chunk13 == 'function':
                                                                address1 = TreeNode(
                                                                    self._input[self._offset : self._offset + 8],
                                                                    self._offset,
                                                                    [],
                                                                )
                                                                self._offset = self._offset + 8
                                                            else:
                                                                address1 = FAILURE
                                                                if self._offset > self._failure:
                                                                    self._failure = self._offset
                                                                    self._expected = []
                                                                if self._offset == self._failure:
                                                                    self._expected.append(
                                                                        ('BashParser::reserved_word', '"function"')
                                                                    )
                                                            if address1 is FAILURE:
                                                                self._offset = index2
        if address1 is not FAILURE:
            elements0.append(address1)
            address2 = FAILURE
            index3 = self._offset
            chunk14, max14 = None, self._offset + 1
            if max14 <= self._input_size:
                chunk14 = self._input[self._offset : max14]
            if chunk14 is not None and Grammar.REGEX_12.search(chunk14):
                address2 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address2 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::reserved_word', '[a-zA-Z0-9_]'))
            self._offset = index3
            if address2 is FAILURE:
                address2 = TreeNode(self._input[self._offset : self._offset], self._offset, [])
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
        self._cache['reserved_word'][index0] = (address0, self._offset)
        return address0

    def _read_delimiter(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['delimiter'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        chunk0, max0 = None, self._offset + 1
        if max0 <= self._input_size:
            chunk0 = self._input[self._offset : max0]
        if chunk0 is not None and Grammar.REGEX_13.search(chunk0):
            address0 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
            self._offset = self._offset + 1
        else:
            address0 = FAILURE
            if self._offset > self._failure:
                self._failure = self._offset
                self._expected = []
            if self._offset == self._failure:
                self._expected.append(('BashParser::delimiter', '[ \\t\\n\\r|&;<>(){}$`"\']'))
        self._cache['delimiter'][index0] = (address0, self._offset)
        return address0

    def _read_spacing(self):
        address0, index0 = FAILURE, self._offset
        cached = self._cache['spacing'].get(index0)
        if cached:
            self._offset = cached[1]
            return cached[0]
        index1, elements0, address1 = self._offset, [], None
        while True:
            chunk0, max0 = None, self._offset + 1
            if max0 <= self._input_size:
                chunk0 = self._input[self._offset : max0]
            if chunk0 is not None and Grammar.REGEX_14.search(chunk0):
                address1 = TreeNode(self._input[self._offset : self._offset + 1], self._offset, [])
                self._offset = self._offset + 1
            else:
                address1 = FAILURE
                if self._offset > self._failure:
                    self._failure = self._offset
                    self._expected = []
                if self._offset == self._failure:
                    self._expected.append(('BashParser::spacing', '[ \\t]'))
            if address1 is not FAILURE:
                elements0.append(address1)
            else:
                break
        if len(elements0) >= 0:
            address0 = TreeNode(self._input[index1 : self._offset], index1, elements0)
            self._offset = self._offset
        else:
            address0 = FAILURE
        self._cache['spacing'][index0] = (address0, self._offset)
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
        tree = self._read_command_line()
        if tree is not FAILURE and self._offset == self._input_size:
            return tree
        if not self._expected:
            self._failure = self._offset
            self._expected.append(('BashParser', '<EOF>'))
        raise ParseError(format_error(self._input, self._failure, self._expected))


class ParseError(SyntaxError):
    pass


def parse(input, actions=None, types=None):
    parser = Parser(input, actions, types)
    return parser.parse()


def format_error(input, offset, expected):
    lines = input.split('\n')
    line_no, position = 0, 0

    while position <= offset:
        position += len(lines[line_no]) + 1
        line_no += 1

    line = lines[line_no - 1]
    message = 'Line ' + str(line_no) + ': expected one of:\n\n'

    for pair in expected:
        message += '    - ' + pair[1] + ' from ' + pair[0] + '\n'

    number = str(line_no)
    while len(number) < 6:
        number = ' ' + number

    message += '\n' + number + ' | ' + line + '\n'
    message += ' ' * (len(line) + 10 + offset - position)
    return message + '^'
