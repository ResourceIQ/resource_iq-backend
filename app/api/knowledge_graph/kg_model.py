# app/models/graph_models.py
from neomodel import (
    FloatProperty,
    IntegerProperty,
    RelationshipTo,
    StringProperty,
    StructuredNode,
    StructuredRel,
)


# --- Relationship Models ---
class SimilarityRel(StructuredRel):
    score = FloatProperty(required=True)

# --- Node Models ---
class Author(StructuredNode):
    login = StringProperty(unique_index=True, required=True)

class Component(StructuredNode):
    name = StringProperty(unique_index=True, required=True)

class File(StructuredNode):
    path = StringProperty(unique_index=True, required=True)

class Label(StructuredNode):
    name = StringProperty(unique_index=True, required=True)

class Epic(StructuredNode):
    key = StringProperty(unique_index=True, required=True)
    summary = StringProperty()

class JiraIssue(StructuredNode):
    key = StringProperty(unique_index=True, required=True)
    summary = StringProperty()
    status = StringProperty()
    epic_key = StringProperty()
    url = StringProperty()

    # Relationships mapping out from JiraIssue
    epic = RelationshipTo('Epic', 'BELONGS_TO')
    components = RelationshipTo('Component', 'HAS_COMPONENT')

class PR(StructuredNode):
    id = IntegerProperty(unique_index=True, required=True)
    number = IntegerProperty()
    title = StringProperty()
    url = StringProperty()
    author_login = StringProperty()
    repo = StringProperty()

    # Relationships mapping out from PR
    author = RelationshipTo('Author', 'AUTHORED_BY')
    repo_component = RelationshipTo('Component', 'IN_REPO')
    modified_files = RelationshipTo('File', 'MODIFIES')
    labels = RelationshipTo('Label', 'HAS_LABEL')
    resolves = RelationshipTo('JiraIssue', 'RESOLVES')
    similar_to = RelationshipTo('PR', 'SIMILAR_TO', model=SimilarityRel)
