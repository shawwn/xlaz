import re
import sys
from copy import copy, deepcopy
from dataclasses import dataclass
from enum import auto, Enum
from functools import lru_cache
from typing import Union

from xlaz import primitive_util
from xlaz.pb.tensorflow.compiler.xla import xla_data_pb2 as xd

@lru_cache
def LazyRE2(pattern):
  return re.compile(pattern)

kEOF = -1
kError = -2

class TokKind(Enum):
  # Markers
  kEof = auto()
  kError = auto()
  # Tokens with no info.
  kEqual = "="
  kComma = ","
  kColon = ":"
  kAsterisk = "*"
  kLsquare = "["
  kRsquare = "]"
  kLbrace = "{"
  kRbrace = "}"
  kLparen = "("
  kRparen = ")"
  kDots = "..."

  kArrow = "->"
  kLeq = "<="

  # Keywords
  kw_HloModule = "HloModule"
  kw_ENTRY = "ENTRY"
  kw_ROOT = "ROOT"
  kw_true = "true"
  kw_false = "false"
  kw_maximal = "maximal"
  kw_replicated = "replicated"
  kw_manual = "manual"
  kw_last_tile_dim_replicate = "last_tile_dim_replicate"
  kw_inf = "inf"
  kNegInf = "-inf"
  # Typed tokens.
  kPrimitiveType   = auto() # F32, PRED, etc.
  kName            = auto() # %foo
  kAttributeName   = auto() # dimensions=
  kDimLabels       = auto() # [0-9bf?]{2,}_[0-9io?]{2,}->[0-9bf?]{2,}
  kDxD             = auto() # [0-9]+(x[0-9]+)+
  kPad             = auto() # [0-9]+_[0-9]+(_[0-9]+)?(x[0-9]+_[0-9]+(_[0-9]+)?)*
  kIdent           = auto() # other identifiers
  kString          = auto() # "abcd\"\n"
  kInt             = auto() # 42
  kDecimal         = auto() # 4.2

class BufferPointer:
  def __init__(self, buf=None, offset=0, length=None):
    if offset < 0:
      raise ValueError('offset < 0')
    self.buf_ = getattr(buf, 'buf_', buf) if buf is not None else []
    self.offset_ = offset
    self.length_ = length
  def __int__(self):
    return self.offset_
  def __new__(cls, buf=None, offset=0, length=None):
    if buf is None:
      return None
    self = object.__new__(cls)
    return self
  def offset(self, other):
    if isinstance(other, self.__class__):
      assert self.same_buffer(other)
    return getattr(other, 'offset_', other)
  def add(self, other):
    assert isinstance(other, int)
    return BufferPointer(self.buf_, self.offset_ + other, self.length_)
  def sub(self, other):
    if isinstance(other, self.__class__):
      assert self.same_buffer(other)
      return self.offset_ - other.offset_
    return BufferPointer(self.buf_, self.offset_ - other, self.length_)
  def to(self, ptr):
    assert self.same_buffer(ptr)
    return BufferPointer(self.buf_, self.offset_, self.offset_ + (ptr - self))
  @property
  def value(self): return self.buf_[self.offset_:self.length_]
  def copy(self): return self.add(0)
  def begin(self): return self - self.offset_
  def end(self): return self + len(self)
  def deref(self): assert len(self) > 0; return self.buf_[self.offset_]
  def same_buffer(self, other):
    if not isinstance(other, self.__class__):
      return False
    if not isinstance(other.buf_, self.buf_.__class__):
      return False
    if hasattr(self.buf_, '__array__'):
      return other.buf_ is self.buf_
    else:
      return other.buf_ == self.buf_
  def __add__(self, other): return self.add(other)
  def __radd__(self, other): return self.add(other)
  def __iadd__(self, other): self.offset_ += self.offset(other); return self
  def __sub__(self, other): return self.sub(other)
  def __rsub__(self, other): return self.sub(other)
  def __isub__(self, other): self.offset_ -= self.offset(other); return self
  def __len__(self): return len(self.value)
  def __repr__(self): return repr(self.value)
  def __str__(self): return str(self.value)
  def __ne__(self, other): return not (self == other)
  def __eq__(self, other): return self.same_buffer(other) and self.offset_ == other.offset_
  def __lt__(self, other): return id(self.buf_) < id(other.buf_) if not self.same_buffer(other) else self.offset_ < other.offset_
  def __le__(self, other): return id(self.buf_) <= id(other.buf_) if not self.same_buffer(other) else self.offset_ <= other.offset_
  def __gt__(self, other): return id(self.buf_) > id(other.buf_) if not self.same_buffer(other) else self.offset_ > other.offset_
  def __ge__(self, other): return id(self.buf_) >= id(other.buf_) if not self.same_buffer(other) else self.offset_ >= other.offset_

class HloLexer:
  @dataclass
  class TokenState:
    token_start: BufferPointer = BufferPointer()
    current_kind: TokKind = TokKind.kEof
    str_val: str = ''
    int64_val: int = 0
    decimal_val: float = 0.0
    primitive_type_val: xd.PrimitiveType = xd.PRIMITIVE_TYPE_INVALID
    def copy(self):
      return self.__class__(
        self.token_start.copy(),
        self.current_kind,
        self.str_val,
        self.int64_val,
        self.decimal_val,
        self.primitive_type_val
      )
  @dataclass
  class LineNoCacheTy:
    last_query: BufferPointer = None
    line_no_of_query: int = 0
  def __init__(self, buf):
    self.data_ = copy(buf)
    self.buf_ = BufferPointer(self.data_)
    self.current_ptr_ = self.buf_.begin()
    self.token_state_ = self.TokenState()
    self.token_state_.token_start = self.current_ptr_.copy()
    self.line_no_cache_ = self.LineNoCacheTy()
  def PeekCurrentChar(self) -> Union[str, TokKind]:
    if self.current_ptr_ == self.buf_.end():
      return kEOF
    current_char = self.current_ptr_.deref()
    if current_char == '\0':
      #'\0' should not appear in the middle of the string.
      return kError
    return current_char
  def GetNextChar(self) -> Union[str, TokKind]:
    current_char = self.PeekCurrentChar()
    if current_char != kEOF and current_char != kError:
      self.current_ptr_ += 1
    return current_char
  def CanDereference(self, ptr):
    return ptr is not None and ptr < self.buf_.end() and ptr >= self.buf_.begin()
  def Lex(self) -> TokKind:
    self.token_state_.current_kind = self.LexToken()
    return self.GetKind()
  def GetKind(self) -> TokKind:
    return self.token_state_.current_kind
  LocTy = BufferPointer
  def GetLoc(self) -> LocTy:
    """Returns the location of the current token."""
    return self.token_state_.token_start.copy()
  def GetLineAndColumn(self, location: LocTy) -> (int, int):
    """Returns the line and column of a location in the buffer."""
    line_no = 1
    start = self.buf_.begin()
    ptr = start.copy()
    #   if (line_no_cache_.last_query && CanDereference(line_no_cache_.last_query) &&
    #       line_no_cache_.last_query <= location) {
    #     ptr = line_no_cache_.last_query;
    #     line_no = line_no_cache_.line_no_of_query;
    #   }
    if self.line_no_cache_.last_query is not None \
            and self.CanDereference(self.line_no_cache_.last_query) \
            and self.line_no_cache_.last_query <= location:
      ptr = self.line_no_cache_.last_query.copy()
      line_no = self.line_no_cache_.line_no_of_query
    end = self.buf_.end()
    while ptr != location:
      assert ptr < end
      if ptr.deref() == '\n':
        line_no += 1
      ptr += 1
    # Update the line number cache.
    self.line_no_cache_.last_query = ptr.copy()
    self.line_no_cache_.line_no_of_query = line_no
    line_offset = StringPieceFromPointers(start, ptr).value.rfind('\n')
    if line_offset < 0:
      line_offset = 0
    return (line_no, ptr - start - line_offset)
  def GetLine(self, loc: LocTy) -> BufferPointer:
    """Returns the whole line given the location."""
    if not self.CanDereference(loc):
      return BufferPointer("LINE OUT OF RANGE")
    line_start = StringPieceFromPointers(self.buf_.begin(), loc + 1).value.rfind('\n')
    start = self.buf_.begin() if line_start < 0 else (self.buf_.begin() + line_start + 1)
    line_end = StringPieceFromPointers(loc, self.buf_.end()).value.find('\n')
    end = self.buf_.end() if line_end < 0 else (loc + line_end)
    return StringPieceFromPointers(start, end)
  def LookAhead(self) -> TokKind:
    """Looks ahead one token and returns it. Lexer state is unchanged."""
    if self.GetKind() in [TokKind.kEof, TokKind.kError]:
      return self.GetKind()
    old_current_ptr = self.current_ptr_.copy()
    old_current_state = self.token_state_.copy()
    try:
      self.Lex()
      kind = self.GetKind()
      return kind
    finally:
      self.token_state_ = old_current_state
      self.current_ptr_ = old_current_ptr
  def LexToken(self) -> TokKind:
    while True:
      self.token_state_.token_start = self.current_ptr_.copy()
      current_char = self.GetNextChar()
      if current_char == kEOF:
        # Hit the end of the input buffer.
        return TokKind.kEof
      elif current_char == kError:
        # Hit an invalid character in the input buffer.
        return TokKind.kError
      elif current_char in [' ', '\t', '\n', '\r']:
        # Ignore whitespace.
        continue
      elif current_char.isnumeric() or current_char == '-':
        if current_char == '-' and self.PeekCurrentChar() == '>':
          self.current_ptr_ += 1
          return TokKind.kArrow
        return self.LexNumberOrPattern();
      elif current_char == '=':
        return TokKind.kEqual
      elif current_char == '<':
        if current_char == '<' and self.PeekCurrentChar() == '=':
          self.current_ptr_ += 1
          return TokKind.kLeq
        return TokKind.kError
      elif current_char == ',':
        return TokKind.kComma
      elif current_char == '%':
        return self.LexPercent()
      #       case ':':
      #         return TokKind::kColon;
      elif current_char == ':':
        return TokKind.kColon
      #       case '*':
      #         return TokKind::kAsterisk;
      elif current_char == '*':
        return TokKind.kAsterisk
      #       case '[':
      #         return TokKind::kLsquare;
      elif current_char == '[':
        return TokKind.kLsquare
      #       case ']':
      #         return TokKind::kRsquare;
      elif current_char == ']':
        return TokKind.kRsquare
      #       case '{':
      #         return TokKind::kLbrace;
      elif current_char == '{':
        return TokKind.kLbrace
      #       case '}':
      #         return TokKind::kRbrace;
      elif current_char == '}':
        return TokKind.kRbrace
      #       case '(':
      #         return TokKind::kLparen;
      elif current_char == '(':
        return TokKind.kLparen
      #       case ')':
      #         return TokKind::kRparen;
      elif current_char == ')':
        return TokKind.kRparen
      elif current_char == '/':
        if self.PeekCurrentChar() == '*':
          # This is the start of a /*...*/ delimited comment. Save the current
          # location in case the comment is unterminated so the error message
          # will point to the beginning of the comment.
          # const char* comment_start = current_ptr_;
          comment_start = self.current_ptr_.copy()
          # current_ptr_++;
          self.current_ptr_ += 1
          # Advance until '*/' is found.
          while True:
            # int current = GetNextChar();
            current = self.GetNextChar()
            # if (current == '*' && PeekCurrentChar() == '/') {
            #   // End of comment.
            #   current_ptr_++;
            #   break;
            # }
            if current == '*' and self.PeekCurrentChar() == '/':
              # End of comment.
              self.current_ptr_ += 1
              break
            # if (current == kEOF) {
            #   // Unterminated comment.
            #   current_ptr_ = comment_start;
            #   return TokKind::kError;
            # }
            if current == kEOF:
              # Unterminated comment.
              self.current_ptr_ = comment_start
              return TokKind.kError
            # if (current == kError) {
            #   return TokKind::kError;
            # }
            if current == kError:
              return TokKind.kError
          # Return no token for the comment. Keep lexing.
          continue
        elif self.PeekCurrentChar() == '/':
          # This is the start of a '//' delimited comment. Throw away
          # everything until end of line or file. The end-of-line character(s)
          # are left unlexed in the buffer which is harmless because these are
          # skipped later by the lexer. This approach enables support for
          # different end-of-line encodings.
          while True:
            current = self.PeekCurrentChar()
            if current == kEOF or current == '\n' or current == '\r':
              break
            if current == kError:
              return TokKind.kError
            self.current_ptr_ += 1
          continue
        # A lone '/' is an error.
        return TokKind.kError
      elif current_char == '.':
        if self.PeekCurrentChar() == '.':
          self.current_ptr_ += 1
          if self.PeekCurrentChar() == '.':
            self.current_ptr_ += 1
            return TokKind.kDots
        return TokKind.kError
      elif current_char == '"':
        return self.LexString()
      else:
        # [a - zA - Z_]
        if current_char.isalpha() or current_char == '_':
          return self.LexIdentifier()
        return TokKind.kError
  def LexIdentifier(self):
    while IsIdentifierChar(self.PeekCurrentChar()):
      self.current_ptr_ += 1
    # If followed by ':', it's a name.
    if self.PeekCurrentChar() == ':':
      self.token_state_.str_val = self.token_state_.token_start.to(self.current_ptr_)
      self.current_ptr_ += 1 # skip ':'
      return TokKind.kName
    # If followed by '=', it's a attribute name.
    if self.PeekCurrentChar() == '=':
      self.token_state_.str_val = self.token_state_.token_start.to(self.current_ptr_)
      self.current_ptr_ += 1 # skip '='
      return TokKind.kAttributeName
    identifier = StringPieceFromPointers(self.token_state_.token_start, self.current_ptr_)
    # Primitive type strings are reserved words. The exception is 'tuple' whose
    # type is represented using nested parentheses without the string 'tuple'.
    #   if (primitive_util::IsPrimitiveTypeName(identifier)) {
    #     PrimitiveType primitive_type =
    #         primitive_util::StringToPrimitiveType(identifier).ValueOrDie();
    #     if (primitive_type != TUPLE) {
    #       token_state_.primitive_type_val = primitive_type;
    #       return TokKind::kPrimitiveType;
    #     }
    #   }
    if primitive_util.IsPrimitiveTypeName(identifier):
      primitive_type = primitive_util.StringToPrimitiveType(identifier)
      if primitive_type != xd.TUPLE:
        self.token_state_.primitive_type_val = primitive_type
        return TokKind.kPrimitiveType
    # if (identifier == "nan") {
    #   absl::optional<int64_t> payload;
    #   if (PeekCurrentChar() == '(') {
    #     absl::string_view consumable =
    #         StringPieceFromPointers(current_ptr_, buf_.end());
    #     payload = LexNanPayload(consumable);
    #     if (!payload.has_value()) {
    #       return TokKind::kError;
    #     }
    #   }
    #   token_state_.decimal_val = NanWithSignAndPayload<double>(
    #       /*sign=*/false, payload.value_or(QuietNanWithoutPayload<double>()));
    #   return TokKind::kDecimal;
    # }
    if str(identifier) == "nan":
      payload = None
      if self.PeekCurrentChar() == '(':
        consumable = StringPieceFromPointers(self.current_ptr_, self.buf_.end())
        payload = self.LexNanPayload(consumable)
        if payload is None:
          return TokKind.kError
      if payload is None:
        val = self.QuietNanWithoutPayload(float)
      else:
        val = self.NanWithSignAndPayload(float, sign=True, nan_payload=payload)
      return TokKind.kDecimal
    for kw in [
      "true",
      "false",
      "inf",
      "HloModule",
      "ENTRY",
      "ROOT",
      "maximal",
      "replicated",
      "manual",
      "last_tile_dim_replicate",
      ]:
      if str(identifier) == kw:
        return getattr(TokKind, "kw_" + kw)
    # {
    #   absl::string_view consumable =
    #       StringPieceFromPointers(token_state_.token_start, buf_.end());
    #   static LazyRE2 dim_labels_pattern = {
    #       R"([0-9bf?]{2,}_[0-9io?]{2,}->[0-9bf?]{2,})"};
    #   if (RE2::Consume(&consumable, *dim_labels_pattern)) {
    #     current_ptr_ = consumable.begin();
    #     token_state_.str_val.assign(token_state_.token_start, current_ptr_);
    #     return TokKind::kDimLabels;
    #   }
    # }
    self.token_state_.str_val = str(identifier)
    return TokKind.kIdent
  # Lex integer and floating-point values, -inf, and patterns for dim labels,
  # dxd (e.g. 1x2x3), and pad.
  #
  # fp with exp ::= [-]?([0-9]+|[0-9]+[.][0-9]*|[0-9]*[.][0-9]+)([eE][+-]?[0-9]+)
  # fp without exp ::= [-]?([0-9]+[.][0-9]*|[0-9]*[.][0-9]+)
  # dim_labels_pattern ::= [0-9bf]{2,}_[0-9io]{2,}->[0-9bf]{2,}
  # dxd_pattern ::= [0-9]+(x[0-9]+)+
  # pad_pattern ::=
  #   [-]?[0-9]+_[-]?[0-9]+(_[0-9]+)?(x[-]?[0-9]+_[-]?[0-9]+(_[0-9]+)?)*
  # int ::=  [-]?[0-9]+
  # negative inf ::= '-inf'
  float_pattern = LazyRE2(r"([-]?((\d+|\d+[.]\d*|\d*[.]\d+)([eE][+-]?\d+))|[-]?(\d+[.]\d*|\d*[.]\d+))")
  dim_labels_pattern = LazyRE2(r"([0-9bf]{2,}_[0-9io]{2,}->[0-9bf]{2,})")
  dxd_pattern = LazyRE2(r"([0-9]+(x[0-9]+)+)")
  pad_pattern = LazyRE2(r"([-]?[0-9]+_[-]?[0-9]+(_[0-9]+)?(x[-]?[0-9]+_[-]?[0-9]+(_[0-9]+)?)*)")
  int_pattern = LazyRE2(r"([-]?\d+)")
  neg_inf = LazyRE2(r"-inf")
  neg_nan = LazyRE2(r"-nan")
  def LexNumberOrPattern(self):
    consumable = StringPieceFromPointers(self.token_state_.token_start, self.buf_.end())
    s = self.Consume(consumable, self.float_pattern)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      self.token_state_.decimal_val = float(s)
      return TokKind.kDecimal
    s = self.Consume(consumable, self.dim_labels_pattern)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      self.token_state_.str_val = str(s)
      return TokKind.kDimLabels
    s = self.Consume(consumable, self.dxd_pattern)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      self.token_state_.str_val = str(s)
      return TokKind.kDxD
    s = self.Consume(consumable, self.pad_pattern)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      self.token_state_.str_val = str(s)
      return TokKind.kPad
    s = self.Consume(consumable, self.int_pattern)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      self.token_state_.int64_val = int(s)
      return TokKind.kInt
    s = self.Consume(consumable, self.neg_inf)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      return TokKind.kNegInf
    s = self.Consume(consumable, self.neg_nan)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      #  absl::optional<int64_t> payload;
      #  if (PeekCurrentChar() == '(') {
      #    payload = LexNanPayload(consumable);
      #    if (!payload.has_value()) {
      #      return TokKind::kError;
      #    }
      #  }
      payload = None
      if self.PeekCurrentChar() == '(':
        payload = self.LexNanPayload(consumable)
        if payload is not None:
          return TokKind.kError
      #  token_state_.decimal_val = NanWithSignAndPayload<double>(
      #      /*sign=*/true, payload.value_or(QuietNanWithoutPayload<double>()));
      if payload is None:
        val = self.QuietNanWithoutPayload(float)
      else:
        val = self.NanWithSignAndPayload(float, sign=True, nan_payload=payload)
      self.token_state_.decimal_val = val
      return TokKind.kDecimal
    return TokKind.kError
  name_pattern = LazyRE2(r"[a-zA-Z_][a-zA-Z0-9_.-]*")
  def LexPercent(self):
    """Lex names after a % character."""
    s = self.Consume(self.current_ptr_, self.name_pattern)
    if s is not None:
      self.token_state_.str_val = str(s)
      return TokKind.kName
    return TokKind.kError
  escaping_pattern = LazyRE2(r'("([^"\\]|\\.)*")')
  def LexString(self):
    """Lexes quoted string with escaping characters. If matched, the quoted string
    will be unescaped and stored to token_state_.str_val."""
    consumable = StringPieceFromPointers(self.token_state_.token_start, self.buf_.end())
    s = self.Consume(consumable, self.escaping_pattern)
    if s is not None:
      self.current_ptr_ = consumable.copy()
      raw = StringPieceFromPointers(self.token_state_.token_start + 1, self.current_ptr_ - 1)
      ok, v = CUnescape(raw)
      if not ok:
        # LOG(ERROR) << "Failed unescaping string: " << raw << ". error: " << error;
        print(f'Failed unescaping string: {str(raw)!r}. error: {v}', file=sys.stderr)
        return TokKind.kError
      else:
        self.token_state_.str_val = str(v)
        return TokKind.kString
    return TokKind.kError
  def Consume(self, consumable: BufferPointer, pattern: re.Pattern):
    #rx = LazyRE2(pattern)
    match = pattern.match(str(consumable))
    if match:
      consumable += match.start()
      consumable += match.end() - match.start()
      return match.group()

def IsIdentifierChar(c: str):
  return c.isalpha() or c.isnumeric() or c in ['.', '_', '-']

def StringPieceFromPointers(a, b) -> BufferPointer:
  return a.to(b)

def CUnescape(source: BufferPointer):
  # TODO: unescape C strings properly. See CUnescape at ~/ml/abseil-cpp/absl/strings/escaping.cc:849
  return True, str(source)
