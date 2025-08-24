from app.extensions import db, bcrypt
from flask_login import UserMixin
from datetime import datetime
import base64


class UserCompany(db.Model):
    __tablename__ = 'user_companies'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id', ondelete='CASCADE'), nullable=False)

    company = db.relationship('CompanyInfo', backref='user_companies', lazy=True)


# Task Management Models

class ProjectMember(db.Model):
    __tablename__ = 'project_members'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    is_reviewer = db.Column(db.Boolean, default=False)

    # Relationships
    project = db.relationship('Project', backref=db.backref('project_members', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('project_memberships', cascade='all, delete-orphan'))

class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    key = db.Column(db.String(10), nullable=False)
    description = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'))
    lead_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    status = db.Column(db.String(50))
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    project_type_id = db.Column(db.Integer, db.ForeignKey('project_types.id'), nullable=False)
    project_type = db.Column(db.String(50), nullable=False)  # Add this line
    allow_due_date_assignment = db.Column(db.Boolean, default=False)  # 1 if task creator can assign due date, 0 otherwise

    # Relationships
    company = db.relationship('CompanyInfo', backref='company_projects')
    lead = db.relationship('User', backref='led_projects')
    epics = db.relationship('Epic', backref='project', lazy=True)
    boards = db.relationship('TaskBoard', backref='project', lazy=True)

    lead = db.relationship('User', foreign_keys=[lead_id], backref='led_projects')
    team = db.relationship('User', 
                            secondary='project_members',
                            secondaryjoin='and_(ProjectMember.project_id == Project.id)',
                            primaryjoin='Project.id == ProjectMember.project_id',
                            backref=db.backref('team_projects', lazy='dynamic'))
    
    reviewers = db.relationship('User', 
                                secondary='project_members',
                                secondaryjoin='and_(ProjectMember.project_id == Project.id, ProjectMember.is_reviewer == True)',
                                primaryjoin='Project.id == ProjectMember.project_id',
                                backref=db.backref('review_projects', lazy='dynamic'))
    
    categories = db.relationship('TaskCategory', backref='project', lazy=True)
    type = db.relationship('ProjectType', backref=db.backref('project_list', lazy=True))

    # document_reviewers = db.relationship(
    #     'DocumentReviewer', 
    #     primaryjoin="and_(DocumentReviewer.project_id == Project.id, DocumentReviewer.type_id == 1)",
    #     backref="project_standard",
    #     viewonly=True
    # )

    @property
    def team(self):
        """
        Returns a list of team members (non-reviewers)
        """
        # Get the ProjectMember associations for this project
        project_members = ProjectMember.query.filter_by(
            project_id=self.id
        ).all()
        
        # Return the associated user
        return [pm.user for pm in project_members]
    
    @property
    def team_members(self):
        """
        Alias for team to maintain backwards compatibility
        """
        return self.team


class ProjectType(db.Model):
    __tablename__ = 'project_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

class ProjectTaskStatus(db.Model):
    __tablename__ = 'task_project_statuses'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(20), nullable=True)
    order_index = db.Column(db.Integer, nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    task_status_id = db.Column(db.Integer, db.ForeignKey('task_statuses.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    # Relationships
    task_status = db.relationship('TaskStatus', backref='project_statuses')
    project = db.relationship('Project', backref='project_statuses')
    
    # Ensure uniqueness of status within a project
    __table_args__ = (
        db.UniqueConstraint('task_status_id', 'project_id', name='uq_project_task_status'),
    )

class TaskBoard(db.Model):
    __tablename__ = 'task_boards'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    board_type = db.Column(db.String(50))
    is_default = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'))

    # Relationships
    creator = db.relationship('User', backref='created_boards')
    company = db.relationship('CompanyInfo', backref='company_boards')
    columns = db.relationship('TaskColumn', backref='board', lazy=True)

class TaskColumn(db.Model):
    __tablename__ = 'task_columns'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    board_id = db.Column(db.Integer, db.ForeignKey('task_boards.id'))
    order = db.Column(db.Integer, nullable=False)
    wip_limit = db.Column(db.Integer)
    
    # Relationship added here, but connected in Task model
    tasks = db.relationship('Task', backref='task_column', lazy=True)

class Epic(db.Model):
    __tablename__ = 'epics'
    
    id = db.Column(db.Integer, primary_key=True)
    epic_key = db.Column(db.String(20), unique=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    status = db.Column(db.String(50))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    progress = db.Column(db.Integer, default=0)
    priority = db.Column(db.String(20))
    color = db.Column(db.String(7))

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_epics')
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_epics')
    stories = db.relationship('Story', backref='epic', lazy=True)
    tasks = db.relationship('Task', backref='direct_epic', lazy=True)

class Story(db.Model):
    __tablename__ = 'stories'
    
    id = db.Column(db.Integer, primary_key=True)
    story_key = db.Column(db.String(20), unique=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    epic_id = db.Column(db.Integer, db.ForeignKey('epics.id'))
    status = db.Column(db.String(50))
    story_points = db.Column(db.Integer)
    priority = db.Column(db.String(20))
    acceptance_criteria = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_stories')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_stories')
    tasks = db.relationship('Task', backref='story', lazy=True)

class TaskComment(db.Model):
    __tablename__ = 'task_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='comments', foreign_keys=[user_id])

class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    file_name = db.Column(db.String(255))
    file_path = db.Column(db.String(255))
    file_data = db.Column(db.LargeBinary)  # Add this field to store binary data
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    uploader = db.relationship('User', backref='attachments', foreign_keys=[uploaded_by])


class TimeEntry(db.Model):
    __tablename__ = 'time_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    hours = db.Column(db.Float)
    description = db.Column(db.Text)
    entry_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.now)

class TaskWatcher(db.Model):
    __tablename__ = 'task_watchers'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    watch_level = db.Column(db.String(20))
    
    # Add relationship with User model
    user = db.relationship('User', backref=db.backref('watched_tasks', lazy=True))

class TaskStatus(db.Model):
    __tablename__ = 'task_statuses'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(20), nullable=True)
    order_index = db.Column(db.Integer, nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_locked = db.Column(db.Boolean, default=False)

    # You can add relationships or backrefs as needed

class TaskPriority(db.Model):
    __tablename__ = 'task_priorities'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(20), nullable=True)
    order_index = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # You can add relationships or backrefs as needed

class TaskCategory(db.Model):
    __tablename__ = 'task_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(20))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)  # Make this required
    created_at = db.Column(db.DateTime, default=datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    category_lead_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # New field for category lead
    sla_hours = db.Column(db.Integer)  # SLA duration in hours
    attachment_required = db.Column(db.Boolean, default=False, nullable=False)  # New field for attachment requirement

    category_lead = db.relationship('User', foreign_keys=[category_lead_id], backref='led_categories')

    # Ensure uniqueness of category name within a project
    __table_args__ = (
        db.UniqueConstraint('project_id', 'name', name='uq_project_category_name'),
    )

class TaskRecurrence(db.Model):
    __tablename__ = 'task_recurrence'
    
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    recurrence_type = db.Column(db.String(20))
    recurrence_interval = db.Column(db.Integer)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    last_generated = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    issue = db.relationship('Issue', backref='recurrence', uselist=False)

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_key = db.Column(db.String(50), unique=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'))
    epic_id = db.Column(db.Integer, db.ForeignKey('epics.id'))
    column_id = db.Column(db.Integer, db.ForeignKey('task_columns.id'))
    task_type = db.Column(db.String(50))
    estimated_hours = db.Column(db.Float)
    actual_hours = db.Column(db.Float)
    status = db.Column(db.String(50))
    status_id = db.Column(db.Integer, db.ForeignKey('task_project_statuses.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    due_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, onupdate=datetime.now)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'))
    priority_id = db.Column(db.Integer, db.ForeignKey('task_priorities.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('task_categories.id'))
    is_done = db.Column(db.Integer, nullable=False, default=0)
    is_reviewed = db.Column(db.Integer, nullable=False, default=0)
    shipment_id = db.Column(db.Integer, nullable=True)

    status = db.relationship('ProjectTaskStatus', backref='tasks')
    priority = db.relationship('TaskPriority', backref='tasks')
    project = db.relationship('Project', backref='tasks')
    category = db.relationship('TaskCategory', backref='tasks')

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_tasks')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_tasks')
    company = db.relationship('CompanyInfo', backref='company_tasks')
    comments = db.relationship('TaskComment', backref='task', lazy=True)
    attachments = db.relationship('TaskAttachment', backref='task', lazy=True)
    time_entries = db.relationship('TimeEntry', backref='task', lazy=True)
    watchers = db.relationship('TaskWatcher', backref='task', lazy=True)


class TaskHistory(db.Model):
    __tablename__ = 'task_history'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    field_name = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    changed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.now)
    
    task = db.relationship('Task', backref='task_changes')
    user = db.relationship('User', backref='task_changes')

class TaskVisibility(db.Model):
    __tablename__ = 'task_visibility'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    current_owner_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    visibility = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    task = db.relationship('Task', backref=db.backref('visibilities', cascade='all, delete-orphan'))
    owner = db.relationship('User', backref=db.backref('owned_task_visibilities', cascade='all, delete-orphan'))

class QueryUpdate(db.Model):
    __tablename__ = 'query_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    description = db.Column(db.String(255), nullable=False)
    executed_query = db.Column(db.Text, nullable=False)
    done_by = db.Column(db.String(100), nullable=False)
    executed_db_names = db.Column(db.String(255), nullable=False)
    connection_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    
    def __repr__(self):
        return (f"<QueryUpdate(id={self.id}, date={self.date}, description='{self.description}', "
                f"done_by='{self.done_by}', executed_db_names='{self.executed_db_names}', "
                f"connection_name='{self.connection_name}', status='{self.status}')>")
    
class QueryExecutionLog(db.Model):
    __tablename__ = 'query_execution_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    query = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    execution_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    user_id = db.Column(db.Integer, nullable=False) 
    destination_connection_name = db.Column(db.String(255), nullable=False)
    destination_database = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<QueryExecutionLog {self.id} - {self.status}>"
    
# Tasks

class IssueType(db.Model):
    __tablename__ = 'issue_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    is_subtask = db.Column(db.Boolean, default=False)
    project_type_id = db.Column(db.Integer, db.ForeignKey('project_types.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)

class IssueStatus(db.Model):
    __tablename__ = 'issue_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(20))
    order_index = db.Column(db.Integer, nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)  # Make this required
    created_at = db.Column(db.DateTime, default=datetime.now)
    project_type_id = db.Column(db.Integer, db.ForeignKey('project_types.id'), nullable=True)  # New column

    project_type = db.relationship('ProjectType', backref='issue_statuses')


    # Ensure uniqueness of status name within a project
    __table_args__ = (
        db.UniqueConstraint('project_id', 'name', name='uq_project_status_name'),
    )



class IssuePriority(db.Model):
    __tablename__ = 'issue_priorities'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    color = db.Column(db.String(20))
    order_index = db.Column(db.Integer, nullable=False)
    project_type_id = db.Column(db.Integer, db.ForeignKey('project_types.id'))

issue_label_map = db.Table('issue_label_map',
    db.Column('issue_id', db.Integer, db.ForeignKey('issues.id'), primary_key=True),
    db.Column('label_id', db.Integer, db.ForeignKey('issue_labels.id'), primary_key=True)
)

# Then define the Issue class with its relationships
class Issue(db.Model):
    __tablename__ = 'issues'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    issue_type_id = db.Column(db.Integer, db.ForeignKey('issue_types.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('task_categories.id'))
    issue_key = db.Column(db.String(50), nullable=False, unique=True)
    summary = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    epic_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    story_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey('issue_statuses.id'), nullable=False)
    priority_id = db.Column(db.Integer, db.ForeignKey('issue_priorities.id'))
    story_points = db.Column(db.Float)
    original_estimate = db.Column(db.Integer)  # in minutes
    remaining_estimate = db.Column(db.Integer)  # in minutes
    time_spent = db.Column(db.Integer)  # in minutes
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, onupdate=datetime.now)

    # Type relationship
    type = db.relationship('IssueType', backref='issues', lazy=True)
    
    # Status relationship
    status = db.relationship('IssueStatus', backref='issues', lazy=True)
    
    # Priority relationship
    priority = db.relationship('IssuePriority', backref='issues', lazy=True)

    # Category relationship
    # Relationships with explicit foreign keys for issue hierarchy
    epic = db.relationship('Issue', 
                          foreign_keys=[epic_id],
                          remote_side=[id],
                          backref=db.backref('epic_issues', lazy=True))
                          
    parent = db.relationship('Issue',
                           foreign_keys=[parent_id],
                           remote_side=[id],
                           backref=db.backref('subtasks', lazy=True))
    
    story = db.relationship('Issue', 
                          foreign_keys=[story_id],
                          remote_side=[id],
                          backref=db.backref('story_tasks', lazy=True))

    # Other relationships
    project = db.relationship('Project', backref='issues', lazy=True)
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_issues')
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='reported_issues')
    comments = db.relationship('IssueComment', backref='issue', lazy=True)
    history = db.relationship('IssueHistory', backref='issue', lazy=True)
    
    # Label relationship
    labels = db.relationship('IssueLabel', 
                           secondary=issue_label_map,
                           backref=db.backref('issues', lazy=True))   

    # Add validation method
    def validate_relationships(self):
        """Validate that relationships are consistent with issue types"""
        errors = []
        
        # Type-specific validations
        if self.issue_type_id == 2:  # Story
            # A Story must have an Epic parent
            if not self.epic_id:
                errors.append("A Story must be associated with an Epic")
                
            # A Story cannot have a Story parent
            if self.story_id:
                errors.append("A Story cannot be associated with another Story")
                
        elif self.issue_type_id == 3:  # Task
            # A Task can optionally have an Epic and/or Story parent
            if self.epic_id and not Issue.query.get(self.epic_id).issue_type_id == 1:
                errors.append("Epic reference must be an issue of type Epic")
                
            if self.story_id and not Issue.query.get(self.story_id).issue_type_id == 2:
                errors.append("Story reference must be an issue of type Story")
                
        elif self.issue_type_id == 4:  # Bug
            # A Bug can be linked to any issue type except Subtask
            if self.parent_id and Issue.query.get(self.parent_id).issue_type_id == 5:
                errors.append("A Bug cannot be linked directly to a Subtask")
                
        elif self.issue_type_id == 5:  # Subtask
            # A Subtask must have a parent that is Task, Story, or Bug (not Epic or another Subtask)
            if not self.parent_id:
                errors.append("A Subtask must have a parent issue")
            else:
                parent_type = Issue.query.get(self.parent_id).issue_type_id
                if parent_type not in [2, 3, 4]:  # Story, Task, Bug
                    errors.append("A Subtask can only have a Story, Task, or Bug as parent")
        
        return errors


class IssueTypeConstraint(db.Model):
    __tablename__ = 'issue_type_constraints'
    
    id = db.Column(db.Integer, primary_key=True)
    parent_type_id = db.Column(db.Integer, db.ForeignKey('issue_types.id'))
    child_type_id = db.Column(db.Integer, db.ForeignKey('issue_types.id'))
    relationship_type = db.Column(db.String(20))  # 'epic', 'story', 'direct_parent'
    is_required = db.Column(db.Boolean, default=False)
    
    # Add default constraints
    @staticmethod
    def create_default_constraints():
        # Story must belong to Epic
        db.session.add(IssueTypeConstraint(
            parent_type_id=1,  # Epic
            child_type_id=2,   # Story
            relationship_type='epic',
            is_required=True
        ))
        
        # Task can optionally belong to Story
        db.session.add(IssueTypeConstraint(
            parent_type_id=2,  # Story
            child_type_id=3,   # Task
            relationship_type='story',
            is_required=False
        ))
        
        # Subtask must have a parent
        db.session.add(IssueTypeConstraint(
            parent_type_id=3,  # Task
            child_type_id=5,   # Subtask
            relationship_type='direct_parent',
            is_required=True
        ))
        
        # Bug can be linked to any type except another Bug
        for type_id in [1, 2, 3, 5]:  # Epic, Story, Task, Subtask
            db.session.add(IssueTypeConstraint(
                parent_type_id=type_id,
                child_type_id=4,  # Bug
                relationship_type='direct_parent',
                is_required=False
            ))
        
        db.session.commit()


class IssueLink(db.Model):
    __tablename__ = 'issue_links'
    
    id = db.Column(db.Integer, primary_key=True)
    source_issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    target_issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    link_type_id = db.Column(db.Integer, db.ForeignKey('issue_link_types.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    source_issue = db.relationship('Issue', foreign_keys=[source_issue_id], backref='outgoing_links')
    target_issue = db.relationship('Issue', foreign_keys=[target_issue_id], backref='incoming_links')
    link_type = db.relationship('IssueLinkType', backref='links')
    creator = db.relationship('User', backref='created_links')

class IssueLinkType(db.Model):
    __tablename__ = 'issue_link_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    inward_desc = db.Column(db.String(100))  # e.g., "is blocked by"
    outward_desc = db.Column(db.String(100))  # e.g., "blocks"
    
    @staticmethod
    def create_default_link_types():
        default_types = [
            ('Blocks', 'is blocked by', 'blocks'),
            ('Duplicates', 'is duplicated by', 'duplicates'),
            ('Relates', 'relates to', 'relates to'),
            ('Causes', 'is caused by', 'causes')
        ]
        
        for name, inward, outward in default_types:
            db.session.add(IssueLinkType(
                name=name,
                inward_desc=inward,
                outward_desc=outward
            ))
        
        db.session.commit()


class IssueComment(db.Model):
    __tablename__ = 'issue_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, onupdate=datetime.now)
    
    author = db.relationship('User', backref='issue_comments')

class IssueHistory(db.Model):
    __tablename__ = 'issue_history'
    
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    field_name = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    changed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref='issue_changes')

class IssueLabel(db.Model):
    __tablename__ = 'issue_labels'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20))
    
    project = db.relationship('Project', backref='issue_labels')

class IssueAttachment(db.Model):
    __tablename__ = 'issue_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id', ondelete='CASCADE'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_type = db.Column(db.String(100))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    issue = db.relationship('Issue', backref='attachments')
    uploader = db.relationship('User', backref='uploaded_attachments')

