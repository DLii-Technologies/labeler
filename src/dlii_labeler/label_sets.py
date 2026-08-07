from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import IntEnum
import json
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import uuid4


DEFAULT_LABEL_COLORS = (
	"#e6194b",
	"#3cb44b",
	"#ffe119",
	"#4363d8",
	"#f58231",
	"#911eb4",
	"#46f0f0",
	"#f032e6",
	"#bcf60c",
	"#fabebe",
	"#008080",
	"#e6beff",
	"#9a6324",
	"#fffac8",
	"#800000",
	"#aaffc3",
	"#808000",
	"#ffd8b1",
	"#000075",
	"#808080",
)


def _new_id() -> str:
	return str(uuid4())


class MetadataFieldType(IntEnum):
	INTEGER = 0
	STRING = 1
	DECIMAL = 2

	@property
	def display_name(self) -> str:
		return {
			self.INTEGER: "Integer",
			self.STRING: "String",
			self.DECIMAL: "Decimal",
		}[self]


@dataclass
class MetadataField:
	id: str
	name: str
	type: MetadataFieldType = MetadataFieldType.STRING
	decimal_places: int = 2

	@classmethod
	def create(
		cls,
		name: str,
		field_type: MetadataFieldType = MetadataFieldType.STRING,
		decimal_places: int = 2,
	) -> "MetadataField":
		return cls(_new_id(), name, field_type, max(0, int(decimal_places)))

	@classmethod
	def from_dict(cls, data: Any) -> Optional["MetadataField"]:
		if not isinstance(data, dict):
			return None
		field_id = data.get("id")
		name = data.get("name")
		field_type = data.get("type", int(MetadataFieldType.STRING))
		decimal_places = data.get("decimal_places", 2)
		if not isinstance(name, str):
			return None
		if not isinstance(field_id, str) or not field_id:
			field_id = _new_id()
		try:
			field_type = MetadataFieldType(int(field_type))
		except (TypeError, ValueError):
			return None
		if not isinstance(decimal_places, int):
			decimal_places = 2
		return cls(field_id, name, field_type, max(0, decimal_places))

	def to_dict(self) -> dict[str, Any]:
		return {
			"id": self.id,
			"name": self.name,
			"type": int(self.type),
			"decimal_places": self.decimal_places,
		}


@dataclass
class Label:
	id: str
	name: str
	color: str = "#ffffff"
	fields: list[MetadataField] = field(default_factory=list)

	@classmethod
	def create(cls, name: str, color: Optional[str] = None) -> "Label":
		return cls(_new_id(), name, color or DEFAULT_LABEL_COLORS[0])

	@classmethod
	def from_dict(cls, data: Any) -> Optional["Label"]:
		if not isinstance(data, dict):
			return None
		label_id = data.get("id")
		name = data.get("name")
		color = data.get("color", "#ffffff")
		if not isinstance(label_id, str) or not label_id:
			return None
		if not isinstance(name, str):
			return None
		if not isinstance(color, str) or not color:
			color = "#ffffff"

		fields: list[MetadataField] = []
		seen_field_ids: set[str] = set()
		seen_field_names: set[str] = set()
		raw_fields = data.get("fields", [])
		if not isinstance(raw_fields, (list, tuple)):
			raw_fields = []
		for raw_field in raw_fields:
			metadata_field = MetadataField.from_dict(raw_field)
			if (
				metadata_field is None
				or metadata_field.id in seen_field_ids
				or metadata_field.name in seen_field_names
			):
				continue
			fields.append(metadata_field)
			seen_field_ids.add(metadata_field.id)
			seen_field_names.add(metadata_field.name)
		return cls(label_id, name, color, fields)

	def to_dict(self) -> dict[str, Any]:
		return {
			"id": self.id,
			"name": self.name,
			"color": self.color,
			"fields": [metadata_field.to_dict() for metadata_field in self.fields],
		}

	def field(self, field_id: Optional[str]) -> Optional[MetadataField]:
		if not isinstance(field_id, str):
			return None
		return next((metadata_field for metadata_field in self.fields if metadata_field.id == field_id), None)

	def add_field(
		self,
		name: str,
		field_type: MetadataFieldType = MetadataFieldType.STRING,
		decimal_places: int = 2,
	) -> MetadataField:
		metadata_field = MetadataField.create(name, field_type, decimal_places)
		self.fields.append(metadata_field)
		return metadata_field

	def remove_field(self, field_id: str) -> bool:
		for index, metadata_field in enumerate(self.fields):
			if metadata_field.id == field_id:
				self.fields.pop(index)
				return True
		return False


@dataclass
class LabelSet:
	id: str
	name: str
	labels: list[Label] = field(default_factory=list)
	tombstones: dict[str, Label] = field(default_factory=dict)
	revision: int = 0

	@classmethod
	def create(cls, name: str) -> "LabelSet":
		return cls(_new_id(), name.strip() or "Untitled Label Set")

	@classmethod
	def from_dict(cls, data: Any) -> Optional["LabelSet"]:
		if not isinstance(data, dict):
			return None
		set_id = data.get("id")
		name = data.get("name")
		if not isinstance(set_id, str) or not set_id or not isinstance(name, str):
			return None

		labels: list[Label] = []
		seen_ids: set[str] = set()
		seen_names: set[str] = set()
		for raw_label in data.get("labels", []):
			label = Label.from_dict(raw_label)
			if label is None or label.id in seen_ids or label.name in seen_names:
				continue
			labels.append(label)
			seen_ids.add(label.id)
			seen_names.add(label.name)

		tombstones: dict[str, Label] = {}
		raw_tombstones = data.get("tombstones", [])
		if isinstance(raw_tombstones, dict):
			raw_tombstones = list(raw_tombstones.values())
		for raw_label in raw_tombstones:
			label = Label.from_dict(raw_label)
			if label is None or label.id in seen_ids or label.id in tombstones:
				continue
			tombstones[label.id] = label

		revision = data.get("revision", 0)
		if not isinstance(revision, int):
			revision = 0
		return cls(set_id, name, labels, tombstones, revision)

	def clone(self) -> "LabelSet":
		return deepcopy(self)

	def to_dict(self) -> dict[str, Any]:
		return {
			"id": self.id,
			"name": self.name,
			"labels": [label.to_dict() for label in self.labels],
			"tombstones": [label.to_dict() for label in self.tombstones.values()],
			"revision": self.revision,
		}

	def label(self, label_id: Optional[str], include_tombstones: bool = True) -> Optional[Label]:
		if not isinstance(label_id, str):
			return None
		for label in self.labels:
			if label.id == label_id:
				return label
		if include_tombstones:
			return self.tombstones.get(label_id)
		return None

	def active_label(self, label_id: Optional[str]) -> Optional[Label]:
		if not isinstance(label_id, str):
			return None
		return next((label for label in self.labels if label.id == label_id), None)

	def label_named(self, name: str) -> Optional[Label]:
		return next((label for label in self.labels if label.name == name), None)

	def active_label_ids(self) -> set[str]:
		return {label.id for label in self.labels}

	def class_id(self, label_id: Optional[str]) -> Optional[int]:
		if not isinstance(label_id, str):
			return None
		for index, label in enumerate(self.labels):
			if label.id == label_id:
				return index
		return None

	def add_label(self, name: str, color: Optional[str] = None) -> Label:
		label = Label.create(name.strip(), color or DEFAULT_LABEL_COLORS[len(self.labels) % len(DEFAULT_LABEL_COLORS)])
		self.labels.append(label)
		return label

	def remove_label(self, label_id: str, referenced_ids: Iterable[str] = ()) -> bool:
		for index, label in enumerate(self.labels):
			if label.id != label_id:
				continue
			self.labels.pop(index)
			if label_id in set(referenced_ids):
				self.tombstones[label_id] = label
			return True
		return False

	def synchronize(self, catalog_set: "LabelSet", referenced_ids: Iterable[str]) -> "LabelSet":
		"""Apply a catalog snapshot while retaining referenced removed labels."""
		referenced = set(referenced_ids)
		old_by_id = {label.id: label for label in self.labels}
		old_by_id.update(self.tombstones)
		new_labels = [deepcopy(label) for label in catalog_set.labels]
		catalog_ids = {label.id for label in catalog_set.labels}

		new_tombstones: dict[str, Label] = {}
		for label_id, old_label in old_by_id.items():
			if label_id not in catalog_ids and label_id in referenced:
				new_tombstones[label_id] = deepcopy(old_label)

		return LabelSet(
			id=catalog_set.id,
			name=catalog_set.name,
			labels=new_labels,
			tombstones=new_tombstones,
			revision=catalog_set.revision,
		)

	def merge_missing_from(self, local_set: "LabelSet") -> bool:
		"""Add active labels and fields from a project snapshot to this set."""
		changed = False
		for local_label in local_set.labels:
			global_label = self.active_label(local_label.id)
			if global_label is None:
				self.tombstones.pop(local_label.id, None)
				self.labels.append(deepcopy(local_label))
				changed = True
				continue

			global_field_ids = {metadata_field.id for metadata_field in global_label.fields}
			for local_field in local_label.fields:
				if local_field.id in global_field_ids:
					continue
				global_label.fields.append(deepcopy(local_field))
				global_field_ids.add(local_field.id)
				changed = True
		return changed


class LabelSetCatalog:
	"""The application-wide catalog of shared label sets."""

	FILE_VERSION = 1

	def __init__(self, path: Path | str):
		self._path = Path(path)
		self._sets: dict[str, LabelSet] = {}
		self._load()

	def _load(self) -> None:
		try:
			with self._path.open("r", encoding="utf-8") as file:
				data = json.load(file)
		except (FileNotFoundError, OSError, json.JSONDecodeError):
			return
		for raw_set in data.get("label_sets", []) if isinstance(data, dict) else []:
			label_set = LabelSet.from_dict(raw_set)
			if label_set is not None:
				self._sets[label_set.id] = label_set

	def _write(self) -> None:
		self._path.parent.mkdir(parents=True, exist_ok=True)
		temporary_path = self._path.with_suffix(self._path.suffix + ".tmp")
		with temporary_path.open("w", encoding="utf-8") as file:
			json.dump(
				{
					"version": self.FILE_VERSION,
					"label_sets": [label_set.to_dict() for label_set in self._sets.values()],
				},
				file,
				indent=2,
			)
		temporary_path.replace(self._path)

	def all(self) -> list[LabelSet]:
		return [label_set.clone() for label_set in self._sets.values()]

	def get(self, set_id: Optional[str]) -> Optional[LabelSet]:
		label_set = self._sets.get(set_id) if isinstance(set_id, str) else None
		return label_set.clone() if label_set is not None else None

	def create(self, name: str) -> LabelSet:
		label_set = LabelSet.create(name)
		label_set.revision = 1
		self._sets[label_set.id] = label_set
		self._write()
		return label_set.clone()

	def save(self, label_set: LabelSet) -> LabelSet:
		updated = label_set.clone()
		previous = self._sets.get(updated.id)
		updated.revision = (previous.revision + 1) if previous is not None else max(1, updated.revision)
		self._sets[updated.id] = updated
		self._write()
		return updated.clone()

	def merge_local(self, local_set: LabelSet) -> LabelSet:
		"""Merge project-local additions into the global catalog."""
		catalog_set = self._sets.get(local_set.id)
		if catalog_set is None:
			imported = local_set.clone()
			# Tombstones describe project-local deleted labels, not catalog entries.
			imported.tombstones.clear()
			imported.revision = max(1, imported.revision)
			self._sets[imported.id] = imported
			self._write()
			return imported.clone()

		merged = catalog_set.clone()
		if merged.merge_missing_from(local_set):
			return self.save(merged)
		return merged

	def delete(self, set_id: str) -> bool:
		if set_id not in self._sets:
			return False
		del self._sets[set_id]
		self._write()
		return True


def collect_annotation_label_references(data: Any) -> tuple[list[str], set[str]]:
	"""Return legacy names and UUIDs referenced by serialized activity data."""
	legacy_names: list[str] = []
	legacy_seen: set[str] = set()
	label_ids: set[str] = set()

	def visit(value: Any) -> None:
		if isinstance(value, dict):
			label_id = value.get("label_id")
			if isinstance(label_id, str) and label_id:
				label_ids.add(label_id)
			legacy_name = value.get("label")
			if isinstance(legacy_name, str) and legacy_name and legacy_name not in legacy_seen:
				legacy_seen.add(legacy_name)
				legacy_names.append(legacy_name)
			for child in value.values():
				visit(child)
		elif isinstance(value, (list, tuple)):
			for child in value:
				visit(child)

	visit(data)
	return legacy_names, label_ids
