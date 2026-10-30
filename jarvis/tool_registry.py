"""Pure, bounded contracts for the four local read-only Jalon 3A tools.

Model output is a proposal, never a permission or executable command. Scope
availability is supplied by the trusted owner, separately from JSON arguments.
This module performs no tool, filesystem, network, GUI or database operation.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from types import MappingProxyType
import uuid


PROTOCOL_VERSION = 1
MAX_PROPOSAL_BYTES = 16384
MAX_ARGUMENT_BYTES = 4096
MAX_RESULT_BYTES = 32768
MAX_EVENT_BYTES = MAX_RESULT_BYTES + 4096
STATUSES = frozenset({"proposed", "denied", "authorized", "running", "received",
                      "verified", "error", "cancelled", "interrupted"})
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
_TASK_ID = re.compile(r"[0-9a-f]{32}\Z")
_TIMEZONE = re.compile(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*\Z")
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + str(index) for prefix in ("COM", "LPT") for index in range(1, 10)}


class ToolValidationError(ValueError):
    """A stable machine code plus a safe, non-content user explanation."""
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _invalid(code="invalid_arguments", message="Arguments d'outil invalides."):
    raise ToolValidationError(code, message)


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


def _json_bytes(value, *, limit, code="oversized_result"):
    """Validate JSON types/depth before encoding; never stringify arbitrary objects."""
    nodes = lower_bound_bytes = 0
    def charge(amount):
        nonlocal lower_bound_bytes
        lower_bound_bytes += amount
        if lower_bound_bytes > limit:
            _invalid(code, "Résultat d'outil trop volumineux.")
    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 12 or nodes > 4096:
            _invalid(code, "Structure d'outil trop volumineuse ou trop imbriquée.")
        if isinstance(item, Mapping):
            if any(type(key) is not str or len(key) > 128 for key in item):
                _invalid(code, "Clés de résultat invalides.")
            charge(2)
            for key in item:
                charge(len(key.encode("utf-8")) + 3)
            return {key: visit(child, depth + 1) for key, child in item.items()}
        if type(item) in (tuple, list):
            charge(2)
            return [visit(child, depth + 1) for child in item]
        if type(item) is str:
            # Reject before dumping/copying potentially huge or repeated leaves.
            if len(item) > limit:
                _invalid(code, "Résultat d'outil trop volumineux.")
            charge(len(item.encode("utf-8")) + 2)
            return item
        if item is None or type(item) is bool:
            charge(1)
            return item
        if type(item) is int:
            charge(max(1, item.bit_length() // 4))
            return item
        if type(item) is float and math.isfinite(item):
            charge(1)
            return item
        _invalid(code, "Seules des données JSON finies sont autorisées.")
    try:
        encoded = json.dumps(visit(value), ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (UnicodeError, ValueError, OverflowError, RecursionError) as error:
        if isinstance(error, ToolValidationError):
            raise
        _invalid(code, "Résultat JSON invalide.")
    if len(encoded) > limit:
        _invalid(code, "Résultat d'outil trop volumineux.")
    return encoded


def _generation(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        _invalid("invalid_generation", "Génération d'action invalide.")
    return value


def _task_id(value):
    if type(value) is not str or not _TASK_ID.fullmatch(value):
        _invalid("invalid_task_id", "Identifiant d'action invalide.")
    return value


def _relative_path(value, *, allow_directory):
    if (not isinstance(value, str) or not 0 < len(value) <= 1024
            or any(not char.isprintable() for char in value) or ":" in value
            or value.startswith(("/", "\\"))):
        _invalid("invalid_path", "Un chemin relatif dans le dossier choisi est requis.")
    value = value.replace("\\", "/")
    if value == "." and allow_directory:
        return value
    parts = value.split("/")
    if any(part in {"", ".", ".."} or len(part) > 255 or part.endswith((".", " "))
           or part.split(".", 1)[0].upper() in _RESERVED for part in parts):
        _invalid("invalid_path", "Chemin relatif non autorisé.")
    return value


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    version: str
    description: str
    arguments_schema: Mapping
    effect: str
    allowed_scope: str
    timeout_seconds: float
    max_result_bytes: int
    permission: str
    verification_method: str

    def __post_init__(self):
        object.__setattr__(self, "arguments_schema", _freeze(self.arguments_schema))

    def schema(self):
        """Return a fresh JSON schema; callers cannot mutate the registry."""
        return _thaw(self.arguments_schema)


def _object(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


_DEFINITIONS = (
    ToolDefinition("system.get_datetime", "1.0", "Lire l'horloge système actuelle et une date relative.",
        _object({"kind": {"type": "string", "enum": ["datetime", "time", "date", "weekday"], "default": "datetime"},
                 "timezone": {"type": "string", "minLength": 1, "maxLength": 128},
                 "days": {"type": "integer", "minimum": -36600, "maximum": 36600, "default": 0}}),
        "read_only", "system_clock", 2., 8192, "allow_local_read", "clock_schema_and_calendar_consistency"),
    ToolDefinition("system.get_basic_info", "1.0", "Lire les informations système non personnelles disponibles.",
        _object({}), "read_only", "non_sensitive_system", 3., 8192,
        "allow_local_read", "system_api_and_result_schema"),
    ToolDefinition("files.list_selected_directory", "1.0", "Lister un dossier explicitement choisi, sans lire les contenus.",
        _object({"path": {"type": "string", "minLength": 1, "maxLength": 1024, "default": "."}}),
        "read_only", "selected_directory", 5., MAX_RESULT_BYTES,
        "selected_resource", "pinned_handles_and_scope_identity"),
    ToolDefinition("files.get_metadata", "1.0", "Lire les métadonnées d'un fichier autorisé, sans son contenu.",
        _object({"path": {"type": "string", "minLength": 1, "maxLength": 1024}}, ("path",)),
        "read_only", "selected_directory", 3., 8192,
        "selected_resource", "pinned_handles_and_file_identity"),
)
REGISTRY = MappingProxyType({definition.tool_id: definition for definition in _DEFINITIONS})


def get_tool(tool_id):
    if type(tool_id) is not str or tool_id not in REGISTRY:
        _invalid("unknown_tool", "Cet outil n'est pas disponible dans JARVIS.")
    return REGISTRY[tool_id]


def validate_arguments(tool_id, arguments):
    """Validate/canonicalize untrusted args; scope/permissions are not arguments."""
    if not isinstance(arguments, Mapping):
        _invalid()
    if tool_id == "none":
        if arguments:
            _invalid()
        return {}
    definition = get_tool(tool_id)
    schema = definition.arguments_schema
    if (any(type(key) is not str for key in arguments)
            or set(arguments) - set(schema["properties"])
            or set(schema["required"]) - set(arguments)):
        _invalid()
    _json_bytes(arguments, limit=MAX_ARGUMENT_BYTES, code="invalid_arguments")
    result = {}
    for key, property_schema in schema["properties"].items():
        if key not in arguments:
            if "default" in property_schema:
                result[key] = property_schema["default"]
            continue
        value = arguments[key]
        if property_schema["type"] == "integer":
            if type(value) is not int or not property_schema["minimum"] <= value <= property_schema["maximum"]:
                _invalid()
        elif (type(value) is not str or not property_schema.get("minLength", 0) <= len(value)
              <= property_schema.get("maxLength", 128)):
            _invalid()
        if "enum" in property_schema and value not in property_schema["enum"]:
            _invalid()
        if key == "timezone" and not _TIMEZONE.fullmatch(value):
            _invalid("invalid_timezone", "Un identifiant de fuseau IANA est requis.")
        if key == "path":
            value = _relative_path(value, allow_directory=tool_id == "files.list_selected_directory")
        result[key] = value
    if tool_id == "system.get_datetime" and result["kind"] == "time" and result["days"]:
        _invalid("invalid_arguments", "L'heure d'une date future ne peut pas être déduite de l'heure actuelle.")
    return result


@dataclass(frozen=True)
class ToolProposal:
    tool_id: str
    arguments: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if type(self.tool_id) is not str:
            _invalid("unknown_tool", "Proposition d'outil invalide.")
        object.__setattr__(self, "arguments", _freeze(validate_arguments(self.tool_id, self.arguments)))

    def to_dict(self):
        return {"tool": self.tool_id, "arguments": _thaw(self.arguments)}

    @property
    def fingerprint(self):
        return hashlib.sha256(_json_bytes(self.to_dict(), limit=MAX_PROPOSAL_BYTES)).hexdigest()


def parse_proposal(raw):
    """One complete JSON proposal only; no Markdown, coercion, arrays or commands."""
    if type(raw) is not str:
        _invalid("invalid_proposal", "Une proposition JSON complète est requise.")
    try:
        if len(raw.encode("utf-8")) > MAX_PROPOSAL_BYTES:
            _invalid("oversized_proposal", "Proposition d'outil trop volumineuse.")
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    _invalid("duplicate_key", "Clés JSON dupliquées dans la proposition.")
                value[key] = item
            return value
        def constant(_value):
            _invalid("invalid_proposal", "Nombres JSON non finis interdits.")
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ToolValidationError):
            raise
        _invalid("invalid_proposal", "Proposition JSON non conforme ; aucune action exécutée.")
    if type(value) is not dict or set(value) != {"tool", "arguments"}:
        _invalid("invalid_proposal", "Une seule proposition d'outil est autorisée.")
    return ToolProposal(value["tool"], value["arguments"])


def schema_for_proposals():
    """Structured-output schema; validation remains mandatory after generation."""
    choices = [_object({"tool": {"const": definition.tool_id}, "arguments": definition.schema()},
                       ("tool", "arguments")) for definition in REGISTRY.values()]
    choices.append(_object({"tool": {"const": "none"}, "arguments": _object({})}, ("tool", "arguments")))
    return {"oneOf": choices}


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    code: str
    reason: str


def authorize(proposal, *, scope_available=False):
    """Only trusted owner state supplies scope_available; model fields never do."""
    if not isinstance(proposal, ToolProposal) or type(scope_available) is not bool:
        _invalid("invalid_permission_context", "Contexte d'autorisation invalide.")
    if proposal.tool_id == "none":
        return PermissionDecision(False, "no_action", "Aucun outil nécessaire ou autorisé pour cette demande.")
    definition = get_tool(proposal.tool_id)
    if definition.permission == "selected_resource" and not scope_available:
        return PermissionDecision(False, "selection_required", "Choisissez d'abord un dossier à autoriser pour cette action.")
    return PermissionDecision(True, "allowed", "Lecture locale autorisée dans le périmètre défini.")


@dataclass(frozen=True)
class ToolTask:
    task_id: str
    generation: int
    tool_id: str
    arguments: Mapping

    def __post_init__(self):
        _task_id(self.task_id)
        _generation(self.generation)
        get_tool(self.tool_id)  # 'none' is deliberately never executable.
        object.__setattr__(self, "arguments", _freeze(validate_arguments(self.tool_id, self.arguments)))

    @classmethod
    def new(cls, proposal, generation):
        if not isinstance(proposal, ToolProposal):
            _invalid("invalid_proposal", "Proposition validée requise.")
        return cls(uuid.uuid4().hex, generation, proposal.tool_id, proposal.arguments)

    def to_dict(self):
        return {"version": PROTOCOL_VERSION, "task_id": self.task_id, "generation": self.generation,
                "tool": self.tool_id, "arguments": _thaw(self.arguments)}

    @classmethod
    def from_dict(cls, value):
        if (type(value) is not dict or set(value) != {"version", "task_id", "generation", "tool", "arguments"}
                or type(value["version"]) is not int or value["version"] != PROTOCOL_VERSION):
            _invalid("invalid_task", "Enveloppe d'action invalide.")
        return cls(value["task_id"], value["generation"], value["tool"], value["arguments"])


def _verification(value, status):
    if not isinstance(value, Mapping):
        _invalid("invalid_verification", "Vérification structurée requise.")
    if value:
        if (set(value) - {"method", "scope", "passed", "checks", "limitations"}
                or not {"method", "scope", "passed"} <= set(value)
                or type(value["passed"]) is not bool
                or any(type(value[key]) is not str or not 1 <= len(value[key]) <= 160
                       for key in ("method", "scope"))):
            _invalid("invalid_verification", "Description de vérification invalide.")
        for key in ("checks", "limitations"):
            if key in value and (not isinstance(value[key], (tuple, list)) or len(value[key]) > 8
                    or any(type(item) is not str or len(item) > 256 for item in value[key])):
                _invalid("invalid_verification", "Détails de vérification trop volumineux.")
    if status == "verified" and (not value or value["passed"] is not True):
        _invalid("invalid_verification", "Un résultat vérifié exige des contrôles effectivement réussis.")
    _json_bytes(value, limit=3072, code="invalid_verification")
    return _freeze(value)


@dataclass(frozen=True)
class ToolResult:
    task_id: str
    generation: int
    tool_id: str
    status: str
    data: Mapping = field(default_factory=dict)
    verification: Mapping = field(default_factory=dict)

    def __post_init__(self):
        _task_id(self.task_id)
        _generation(self.generation)
        definition = get_tool(self.tool_id)
        if type(self.status) is not str or self.status not in STATUSES or not isinstance(self.data, Mapping):
            _invalid("invalid_result", "Résultat d'action invalide.")
        _json_bytes(self.data, limit=definition.max_result_bytes)
        object.__setattr__(self, "data", _freeze(self.data))
        object.__setattr__(self, "verification", _verification(self.verification, self.status))
        _json_bytes(self.to_dict(), limit=MAX_EVENT_BYTES)

    def to_dict(self):
        return {"version": PROTOCOL_VERSION, "task_id": self.task_id, "generation": self.generation,
                "tool": self.tool_id, "status": self.status, "data": _thaw(self.data),
                "verification": _thaw(self.verification)}

    @classmethod
    def from_dict(cls, value):
        keys = {"version", "task_id", "generation", "tool", "status", "data", "verification"}
        if (type(value) is not dict or set(value) != keys or type(value["version"]) is not int
                or value["version"] != PROTOCOL_VERSION):
            _invalid("invalid_result", "Enveloppe de résultat invalide.")
        return cls(value["task_id"], value["generation"], value["tool"], value["status"],
                   value["data"], value["verification"])
