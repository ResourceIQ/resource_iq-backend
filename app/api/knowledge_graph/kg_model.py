# mypy: disable-error-code=attr-defined

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


class ExperienceRel(StructuredRel):
    level = IntegerProperty(required=True)


# --- Node Models ---
class Resource(StructuredNode):
    github_id = IntegerProperty(unique_index=True, required=True)
    login = StringProperty(index=True)

    # User-declared intent relationships.
    wants_to_work_in = RelationshipTo("Domain", "WANTS_TO_WORK_IN")
    wants_to_learn_skill = RelationshipTo("Skill", "WANTS_TO_LEARN")
    wants_to_learn_language = RelationshipTo("Language", "WANTS_TO_LEARN")
    wants_to_learn_framework = RelationshipTo("Framework", "WANTS_TO_LEARN")
    wants_to_learn_tool = RelationshipTo("Tool", "WANTS_TO_LEARN")

    has_experience_domain = RelationshipTo(
        "Domain", "HAS_EXPERIENCE_WITH", model=ExperienceRel
    )
    has_experience_skill = RelationshipTo(
        "Skill", "HAS_EXPERIENCE_WITH", model=ExperienceRel
    )
    has_experience_language = RelationshipTo(
        "Language", "HAS_EXPERIENCE_WITH", model=ExperienceRel
    )
    has_experience_framework = RelationshipTo(
        "Framework", "HAS_EXPERIENCE_WITH", model=ExperienceRel
    )
    has_experience_tool = RelationshipTo(
        "Tool", "HAS_EXPERIENCE_WITH", model=ExperienceRel
    )


class Component(StructuredNode):
    name = StringProperty(unique_index=True, required=True)


class File(StructuredNode):
    path = StringProperty(unique_index=True, required=True)


class Label(StructuredNode):
    name = StringProperty(unique_index=True, required=True)


class Language(StructuredNode):
    name = StringProperty(unique_index=True, required=True)


class Framework(StructuredNode):
    name = StringProperty(unique_index=True, required=True)


class Domain(StructuredNode):
    slug = StringProperty(unique_index=True, required=True)


class Skill(StructuredNode):
    slug = StringProperty(unique_index=True, required=True)


class Tool(StructuredNode):
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
    epic = RelationshipTo("Epic", "BELONGS_TO")
    components = RelationshipTo("Component", "HAS_COMPONENT")


class PR(StructuredNode):
    identifier = IntegerProperty(unique_index=True, required=True)
    number = IntegerProperty()
    title = StringProperty()
    context = StringProperty()
    url = StringProperty()
    author_login = StringProperty()
    repo = StringProperty()

    # Relationships mapping out from PR
    author = RelationshipTo("Resource", "AUTHORED_BY")
    repo_component = RelationshipTo("Component", "IN_REPO")
    modified_files = RelationshipTo("File", "MODIFIES")
    pr_labels = RelationshipTo("Label", "HAS_LABEL")
    similar_to = RelationshipTo("PR", "SIMILAR_TO", model=SimilarityRel)

    # Entity extraction relationships
    uses_language = RelationshipTo("Language", "USES_LANGUAGE")
    uses_framework = RelationshipTo("Framework", "USES_FRAMEWORK")
    touches_domain = RelationshipTo("Domain", "TOUCHES_DOMAIN")
    demonstrates_skill = RelationshipTo("Skill", "DEMONSTRATES_SKILL")
    uses_tool = RelationshipTo("Tool", "USES_TOOL")
