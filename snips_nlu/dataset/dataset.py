# coding=utf-8
from __future__ import print_function, unicode_literals

import io
from itertools import cycle
from pathlib import Path

import yaml
from deprecation import deprecated
from snips_nlu_ontology import get_builtin_entity_examples

from snips_nlu.__about__ import __version__
from snips_nlu.dataset.entity import Entity
from snips_nlu.dataset.intent import Intent


class DatasetFormatError(TypeError):
    pass


class Dataset(object):
    """Dataset used in the main NLU training API

    Consists of intents and entities data. This object can be built either from
    text files (:meth:`.Dataset.from_files`) or from YAML files
    (:meth:`.Dataset.from_yaml_files`).

    Attributes:
        language (str): language of the intents
        intents (list of :class:`.Intent`): intents data
        entities (list of :class:`.Entity`): entities data
    """

    def __init__(self, language, intents, entities):
        self.language = language
        self.intents = intents
        self.entities = entities
        self._add_missing_entities()
        self._ensure_entity_values()

    @classmethod
    def from_yaml_files(cls, language, filenames):
        # pylint:disable=line-too-long
        """Creates a :class:`.Dataset` from a language and a list of YAML files
        containing intents and entities data

        Each file need not correspond to a single entity nor intent. They can
        consist in several entities and intents merged together in a single
        file.

        A dataset can be defined with a YAML document following the schema
        illustrated in the example below:

        .. code-block:: yaml

            # searchFlight Intent
            ---
            type: intent
            name: searchFlight
            slots:
              - name: origin
                entity: city
              - name: destination
                entity: city
              - name: date
                entity: snips/datetime
            utterances:
              - find me a flight from [origin](Paris) to [destination](New York)
              - I need a flight leaving [date](this weekend) to [destination](Berlin)
              - show me flights to go to [destination](new york) leaving [date](this evening)

            # City Entity
            ---
            type: entity
            name: city
            values:
              - london
              - [new york, big apple]
              - [paris, city of lights]

        Raises:
            DatasetFormatError: When one of the documents present in the YAML
                files has a wrong 'type' attribute, which is not 'entity' nor
                'intent'
            IntentFormatError: When the YAML document of an intent does not
                correspond to the :ref:`expected intent format <yaml_intent_format>`
            EntityFormatError: When the YAML document of an entity does not
                correspond to the :ref:`expected entity format <yaml_entity_format>`
        """
        # pylint:enable=line-too-long
        entities = []
        intents = []
        for filename in filenames:
            with io.open(filename, encoding="utf8") as f:
                for doc in yaml.safe_load_all(f):
                    doc_type = doc.get("type")
                    if doc_type == "entity":
                        entities.append(Entity.from_yaml(doc))
                    elif doc_type == "intent":
                        intents.append(Intent.from_yaml(doc))
                    else:
                        raise DatasetFormatError(
                            "Invalid 'type' value in YAML file '%s': '%s'"
                            % (filename, doc_type))
        return cls(language, intents, entities)

    @classmethod
    @deprecated(deprecated_in="0.18.0", removed_in="0.19.0",
                current_version=__version__,
                details="Use from_yaml_files instead")
    def from_files(cls, language, filenames):
        """Creates a :class:`.Dataset` from a language and a list of intent and
        entity files

        Args:
            language (str): language of the assistant
            filenames (list of str): Intent and entity files.
                The assistant will associate each intent file to an intent,
                and each entity file to an entity. For instance, the intent
                file 'intent_setTemperature.txt' will correspond to the intent
                'setTemperature', and the entity file 'entity_room.txt' will
                correspond to the entity 'room'.
        """
        intent_filepaths = set()
        entity_filepaths = set()
        for filename in filenames:
            filepath = Path(filename)
            stem = filepath.stem
            if stem.startswith("intent_"):
                intent_filepaths.add(filepath)
            elif stem.startswith("entity_"):
                entity_filepaths.add(filepath)
            else:
                raise AssertionError("Filename should start either with "
                                     "'intent_' or 'entity_' but found: %s"
                                     % stem)

        intents = [Intent.from_file(f) for f in intent_filepaths]

        entities = [Entity.from_file(f) for f in entity_filepaths]
        return cls(language, intents, entities)

    def _add_missing_entities(self):
        entity_names = set(e.name for e in self.entities)

        # Add entities appearing only in the intents utterances
        for intent in self.intents:
            for entity_name in intent.entities_names:
                if entity_name not in entity_names:
                    entity_names.add(entity_name)
                    self.entities.append(Entity(name=entity_name))

    def _ensure_entity_values(self):
        entities_values = {entity.name: self._get_entity_values(entity)
                           for entity in self.entities}
        for intent in self.intents:
            for utterance in intent.utterances:
                for chunk in utterance.slot_chunks:
                    if chunk.text is not None:
                        continue
                    try:
                        chunk.text = next(entities_values[chunk.entity])
                    except StopIteration:
                        raise DatasetFormatError(
                            "At least one entity value must be provided for "
                            "entity '%s'" % chunk.entity)
        return self

    def _get_entity_values(self, entity):
        if entity.is_builtin:
            return cycle(get_builtin_entity_examples(
                entity.name, self.language))
        values = [v for utterance in entity.utterances
                  for v in utterance.variations]
        values_set = set(values)
        for intent in self.intents:
            for utterance in intent.utterances:
                for chunk in utterance.slot_chunks:
                    if not chunk.text or chunk.entity != entity.name:
                        continue
                    if chunk.text not in values_set:
                        values_set.add(chunk.text)
                        values.append(chunk.text)
        return cycle(values)

    @property
    def json(self):
        """Dataset data in json format"""
        intents = {intent_data.intent_name: intent_data.json
                   for intent_data in self.intents}
        entities = {entity.name: entity.json for entity in self.entities}
        return dict(language=self.language, intents=intents, entities=entities)