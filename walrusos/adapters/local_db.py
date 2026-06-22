from sqlmodel import create_engine, Session, SQLModel
from walrusos.core.models import Workspace, Agent

class LocalDBAdapter:
    """Manages the highly-indexed local metadata SQLite/pgvector database."""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        SQLModel.metadata.create_all(self.engine)

    def create_workspace(self, workspace: Workspace):
        with Session(self.engine) as session:
            session.add(workspace)
            session.commit()
            
    def create_agent(self, agent: Agent):
        with Session(self.engine) as session:
            session.add(agent)
            session.commit()
