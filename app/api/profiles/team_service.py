from sqlmodel import Session, select

from app.api.profiles.profile_model import ResourceProfile
from app.api.profiles.team_model import Team
from app.api.profiles.team_schema import TeamCreate, TeamUpdate


class TeamService:
    def __init__(self, session: Session):
        self.session = session

    def create_team(self, team_in: TeamCreate) -> Team:
        team = Team(**team_in.model_dump())
        self.session.add(team)
        self.session.commit()
        self.session.refresh(team)
        return team

    def get_team(self, team_id: int) -> Team | None:
        return self.session.get(Team, team_id)

    def list_teams(self, skip: int = 0, limit: int = 100) -> list[Team]:
        statement = select(Team).offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def update_team(self, team_id: int, team_in: TeamUpdate) -> Team | None:
        team = self.get_team(team_id)
        if not team:
            return None

        update_data = team_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(team, key, value)

        self.session.add(team)
        self.session.commit()
        self.session.refresh(team)
        return team

    def delete_team(self, team_id: int) -> bool:
        team = self.get_team(team_id)
        if not team:
            return False

        # Optionally handle profiles belonging to this team
        # For now, we just nullify the team_id in profiles
        profiles = self.session.exec(
            select(ResourceProfile).where(ResourceProfile.team_id == team_id)
        ).all()
        for profile in profiles:
            profile.team_id = None
            self.session.add(profile)

        self.session.delete(team)
        self.session.commit()
        return True

    def add_member(self, team_id: int, profile_id: int) -> bool:
        team = self.get_team(team_id)
        profile = self.session.get(ResourceProfile, profile_id)

        if not team or not profile:
            return False

        profile.team_id = team_id
        self.session.add(profile)
        self.session.commit()
        return True

    def remove_member(self, team_id: int, profile_id: int) -> bool:
        profile = self.session.get(ResourceProfile, profile_id)

        if not profile or profile.team_id != team_id:
            return False

        profile.team_id = None
        self.session.add(profile)
        self.session.commit()
        return True
