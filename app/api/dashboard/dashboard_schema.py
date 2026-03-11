""" dashabrod response schemas """

from pydantic import BaseModel


class TeamMembersCard(BaseModel):
    total: int                   # e.g. 6
    new_this_month: int          # e.g. +2


class TeamUtilizationCard(BaseModel):
    percentage: float            # e.g. 59.0
    message: str                 # e.g. "Monitor closely"


class ActiveTasksCard(BaseModel):
    active_count: int            # e.g. 9
    completed_this_week: int     # e.g. 12


class PendingAssignmentsCard(BaseModel):
    count: int                   # e.g. 5
    message: str                 # e.g. "Needs attention"


class TeamAllocation(BaseModel):
    team_name: str               # e.g. "Design Engineering"
    headcount: int               # e.g. 186


class ResourceUtilizationStatus(BaseModel):
    total_resources: int         # e.g. 41
    utilized: int                # resources currently assigned
    available: int               # resources not assigned


class DashboardResponse(BaseModel):
    team_members: TeamMembersCard
    team_utilization: TeamUtilizationCard
    active_tasks: ActiveTasksCard
    pending_assignments: PendingAssignmentsCard
    resource_allocation_by_team: list[TeamAllocation]
    resource_utilization: ResourceUtilizationStatus
