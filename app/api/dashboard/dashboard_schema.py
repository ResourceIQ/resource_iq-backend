""" dashabrod response schemas """

from pydantic import BaseModel


class TeamMembersCard(BaseModel):
    total: int                   # e.g. 6
    new_this_month: int          # e.g. +2

class DashboardResponse(BaseModel):
    team_members: TeamMembersCard

    