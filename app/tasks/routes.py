from flask import Blueprint, render_template, redirect, url_for, jsonify, request, flash, abort, send_file, current_app
from flask_login import login_required, current_user
from app.models.task_management import (
    Task, Project, Epic, Story, TaskBoard, TaskColumn, 
    TaskComment, TaskAttachment, TimeEntry, TaskWatcher,
    ProjectMember, Issue, IssueComment, IssueHistory,
    IssueLabel, IssueLink, IssuePriority, IssueStatus, IssueType, IssueAttachment,
    TaskCategory, ProjectType, TaskPriority, TaskStatus, TaskHistory, ProjectTaskStatus, 
    IssueTypeConstraint, UserCompany, TaskVisibility
)
from app.models.company import CompanyInfo
from app.models.user import User
from app import db
from datetime import datetime
from sqlalchemy import or_, extract
from datetime import datetime
from .utils import validate_project_dates, calculate_epic_progress
from datetime import timedelta
from sqlalchemy.sql import and_, or_, cast
from sqlalchemy.types import Integer
from sqlalchemy import func
from werkzeug.utils import secure_filename
import io
from app.tasks import tasks_bp
from app.utils import get_sri_lanka_time


status_colors = {
    'Planning': 'secondary',
    'Active': 'success',
    'OnHold': 'warning',
    'Completed': 'info'
}

# ------------- PROJECTS ------------------
@tasks_bp.route("/projects")
@login_required
def projects():
    if current_user.assigned_role.role_name == 'admin':
        # Admin sees all companies and their projects
        project_statuses = TaskStatus.query.order_by(TaskStatus.order_index).all()
        companies = CompanyInfo.query.all()
        
        # Eager load project members
        projects = Project.query.all()
        
        print("All projects fetched for admin")
    else:
        # Regular users see:
        # 1. Projects of their company where they are team members
        project_statuses = TaskStatus.query.order_by(TaskStatus.order_index).all()
        companies = []
        
        # Precise filtering to ensure user is actually a team member
        projects = Project.query.join(ProjectMember)\
            .filter(Project.company_id == current_user.company_id)\
            .distinct().all()

        
        print(f"Projects fetched for user: {[project.name for project in projects]}")


    company_users = User.query.filter_by(company_id=current_user.company_id).all()
    project_statuses = TaskStatus.query.order_by(TaskStatus.order_index).all()

    return render_template('tasks/projects.html',
                         projects=projects,
                         companies=companies,
                         users=company_users,
                         project_statuses=project_statuses)


@tasks_bp.route("/api/companies/<int:company_id>/users")
@login_required
def get_company_users(company_id):
    # Check if user has access to this company
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and current_user.company_id != company_id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    users = User.query.filter(User.company_id==company_id, User.role != 'customer').all()
    return jsonify({
        'users': [{'id': user.id, 'name': user.name} for user in users]
    })

@tasks_bp.route("/api/projects", methods=['POST'])
@login_required
def create_project():
    data = request.get_json()
    print("Received data:", data)  # Debug log
    
    try:
        # Get project type
        project_type = data.get('project_type', 'general')
        name = data.get('name')
        # Find the corresponding project type ID
        project_type_obj = ProjectType.query.filter_by(name=project_type).first()
        if not project_type_obj:
            return jsonify({'success': False, 'error': 'Invalid project type'})
        
        # Create project
        project = Project(
            name=data['name'],
            project_type=project_type,
            project_type_id=project_type_obj.id,
            description=data.get('description'),
            company_id=int(data['company_id']),
            lead_id=int(data['lead_id']),
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d') if data.get('start_date') else None,
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d') if data.get('end_date') else None,
            status=data['status'],
            allow_due_date_assignment=data.get('allow_due_date_assignment', False),
            key=data.get('key') if data.get('key') else generate_project_key(name)
        )

        db.session.add(project)
        db.session.flush()  # Get project ID

        # Handle team members
        # Handle team members
        if data.get('team_members'):
            team_member_ids = set(map(int, data['team_members']))
            team_member_ids.add(int(data['lead_id']))  # Ensure lead is in team
            
            # This is the problematic part - instead of project.team.extend():
            for user_id in team_member_ids:
                # Create ProjectMember objects explicitly
                project_member = ProjectMember(
                    project_id=project.id,
                    user_id=user_id,
                    is_reviewer=False  # Default value, adjust as needed
                )
                db.session.add(project_member)
        
        # Handle categories for general projects
        if project_type == 'general' and data.get('categories'):
            for category_data in data['categories']:
                category = TaskCategory(
                    name=category_data['name'],
                    color=category_data['color'],
                    project_id=project.id,
                    created_by=current_user.id,
                    category_lead_id=category_data.get('category_lead_id'),
                    sla_hours=category_data.get('sla_hours', 24),  # Default to 24 hours if not provided                            attachment_required=category_data.get('attachment_required', False),  # New field
                    created_at=get_sri_lanka_time()
                )
                db.session.add(category)
                print(f"Added category: {category_data['name']} for project {project.id}")  # Debug log
        
        # Handle project statuses - get data from database
        if project_type == 'general' and data.get('project_status_ids'):
            for status_id in data['project_status_ids']:
                # Fetch the status from the database
                task_status = TaskStatus.query.get(status_id)
                if task_status:
                    project_status = ProjectTaskStatus(
                        name=task_status.name,
                        description=task_status.description,
                        color=task_status.color,
                        order_index=task_status.order_index,
                        is_done=task_status.is_done,
                        task_status_id=task_status.id,
                        project_id=project.id
                    )
                    db.session.add(project_status)
                    print(f"Added project status: {task_status.name} for project {project.id}")  # Debug log
        
        db.session.commit()
        flash('Project created successfully', 'success')
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating project: {str(e)}")  # Debug log
        return jsonify({'success': False, 'error': str(e)})


@tasks_bp.route("/project/<int:project_id>")
@login_required
def project_detail(project_id):
    print(f"DEBUG: Accessing project_detail with project_id={project_id}")
    
    project = Project.query.get_or_404(project_id)
    print(f"DEBUG: Retrieved project {project}")

    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        print(f"DEBUG: User {current_user.id} does not have access to project {project_id}")
        abort(403)

    try:
        # Calculate days remaining
        days_remaining = None
        if project.end_date:
            days_remaining = (project.end_date.date() - get_sri_lanka_time().date()).days
        print(f"DEBUG: Days remaining: {days_remaining}")

        # Common statistics
        common_stats = {
            'total_members': len(project.team),
            'days_remaining': days_remaining,
            'completion_percentage': calculate_project_completion(project)
        }
        print(f"DEBUG: Common stats: {common_stats}")

        # Get project type-specific statistics
        if project.type.name == 'development':  # Changed from project.project_type
            type_stats = get_development_project_stats(project)
        else:
            type_stats = get_general_project_stats(project)
        print(f"DEBUG: Type-specific stats: {type_stats}")

        # Combine stats
        stats = {**common_stats, **type_stats}
        print(f"DEBUG: Final stats: {stats}")

        # Get recent activities
        activities = get_project_activities(project)
        print(f"DEBUG: Retrieved {len(activities)} activities")

        return render_template(
            'tasks/project_detail.html',
            project=project,
            stats=stats,
            activities=activities,
            status_colors=status_colors
        )

    except Exception as e:
        print(f"ERROR: Exception in project_detail: {str(e)}")
        import traceback
        print(traceback.format_exc())

        flash('Error loading project details', 'error')
        return redirect(url_for('tasks.projects'))
    
      
@tasks_bp.route("/api/projects/<int:project_id>/stats")
@login_required
def get_project_stats_api(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Calculate days remaining
        days_remaining = None
        if project.end_date:
            days_remaining = (project.end_date.date() - get_sri_lanka_time().date()).days

        # Get basic stats
        stats = {
            'days_remaining': days_remaining,
            'completion_rate': calculate_project_completion(project),
            'total_members': len(project.team)
        }

        # Add type-specific stats
        if project.project_type == 'development':
            stats.update(get_development_project_stats(project))
        else:
            stats.update(get_general_project_stats(project))

        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        print(f"Error in get_project_stats_api: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/stats")
@login_required
def get_project_stats(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Calculate days remaining - Convert both to date for comparison
        days_remaining = None
        if project.end_date:
            days_remaining = (project.end_date.date() - get_sri_lanka_time().date()).days

        # Base stats
        stats = {
            'total_members': len(project.team),
            'days_remaining': days_remaining,
            'completion_rate': calculate_project_completion(project)
        }

        # Add type-specific stats
        if project.project_type == 'development':
            stats.update({
                'total_epics': Issue.query.filter_by(
                    project_id=project.id,
                    issue_type_id=1
                ).count(),
                'total_stories': Issue.query.filter_by(
                    project_id=project.id,
                    issue_type_id=2
                ).count(),
                'total_tasks': Issue.query.filter_by(
                    project_id=project.id,
                    issue_type_id=3
                ).count(),
                'total_subtasks': Issue.query.filter_by(
                    project_id=project.id,
                    issue_type_id=4
                ).count(),
                'total_bugs': Issue.query.filter_by(
                    project_id=project.id,
                    issue_type_id=5
                ).count(),
            })
        else:
            # Stats for general project
            category_stats = get_category_stats(project)
            stats.update({
                'total_tasks': sum(cat['total'] for cat in category_stats.values()),
                'total_completed': sum(cat['completed'] for cat in category_stats.values()),
                'categories': category_stats
            })

        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        print(f"Error in get_project_stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/statuses")
@login_required
def get_project_statuses(project_id):
    project = Project.query.get_or_404(project_id)
    
    try:
        if project.type.name == 'development':
            statuses = IssueStatus.query.filter(
                IssueStatus.id.in_([1, 2, 3, 4])
            ).order_by(IssueStatus.order_index).all()
        else:
            statuses = ProjectTaskStatus.query.filter_by(
                project_id=project_id
            ).order_by(ProjectTaskStatus.order_index).all()


            
        return jsonify({
            'success': True,
            'statuses': [{
                'id': status.id,
                'name': status.name,
                'color': status.color,
                'order_index': status.order_index
            } for status in statuses]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/team")
@login_required
def get_project_team(project_id):
    project = Project.query.get_or_404(project_id)
    
    try:
        # Get all project members, including reviewers
        project_members = ProjectMember.query.filter_by(project_id=project_id).all()
        
        team_data = []
        processed_user_ids = set()  # Track processed users to avoid duplicates
        
        for pm in project_members:
            member = pm.user
            
            # Skip if user has already been processed
            if member.id in processed_user_ids:
                continue
            
            processed_user_ids.add(member.id)
            
            # Determine assigned count and statistics based on project type
            if project.type.name == 'development':
                assigned_count = Issue.query.filter_by(
                    project_id=project_id, 
                    assignee_id=member.id
                ).count()
            else:
                assigned_count = Task.query.filter_by(
                    project_id=project_id,
                    assigned_to=member.id  
                ).count()
            
            member_data = {
                'id': member.id,
                'name': member.name,
                'role': member.role.role_name,
                'assigned_count': assigned_count,
                'status': 'Active' if member.isactiveYN else 'Inactive',
                'profile_picture': member.profile_picture_base64 if member.profile_picture else None,
                'is_reviewer': pm.is_reviewer  # Add reviewer status
            }
            
            # Preserve the original print debugging
            print(f"Member data for {member.name}:")
            print(f"  ID: {member_data['id']}")
            print(f"  Name: {member_data['name']}")
            print(f"  Role: {member_data['role']}")
            print(f"  Assigned Count: {member_data['assigned_count']}")
            print(f"  Status: {member_data['status']}")
            print(f"  Profile Picture: {'Available' if member_data['profile_picture'] else 'Not Available'}")
            print(f"  Is Reviewer: {member_data['is_reviewer']}")
            
            team_data.append(member_data)
        
        return jsonify({
            'success': True,
            'data': team_data
        })
        
    except Exception as e:
        print(f"Error in get_project_team: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/categories", methods=['POST'])
@login_required
def create_project_category(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Validate input
        if not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'Category name is required'
            }), 400
        
        # Check for existing category with same name in this project
        existing_category = TaskCategory.query.filter_by(
            project_id=project_id, 
            name=data['name']
        ).first()
        
        if existing_category:
            return jsonify({
                'success': False,
                'error': 'A category with this name already exists in the project'
            }), 400
        
        # Create new category
        category = TaskCategory(
            name=data['name'],
            color=data.get('color', '#563d7c'),  # Default color if not provided
            project_id=project_id,
            created_by=current_user.id
        )
        
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Category created successfully',
            'category': {
                'id': category.id,
                'name': category.name,
                'color': category.color
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating category: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to create category',
            'details': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/statuses", methods=['GET', 'POST'])
@login_required
def manage_project_statuses(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validate input
            if not data.get('name'):
                return jsonify({
                    'success': False,
                    'error': 'Status name is required'
                }), 400
            
            # Check for existing status with same name in this project
            existing_status = IssueStatus.query.filter_by(
                project_id=project_id, 
                name=data['name']
            ).first()
            
            if existing_status:
                return jsonify({
                    'success': False,
                    'error': 'A status with this name already exists in the project'
                }), 400
            
            # Get max order index
            max_order = db.session.query(
                db.func.coalesce(db.func.max(IssueStatus.order_index), 0)
            ).filter_by(project_id=project_id).scalar()
            
            # Create new status
            status = IssueStatus(
                name=data['name'],
                color=data.get('color', '#6c757d'),  # Default color if not provided
                order_index=max_order + 1,
                project_id=project_id,
                is_done=data.get('is_done', False)
            )
            
            db.session.add(status)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Status created successfully',
                'status': {
                    'id': status.id,
                    'name': status.name,
                    'color': status.color,
                    'order_index': status.order_index
                }
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating status: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Failed to create status',
                'details': str(e)
            }), 500
    
    # GET request - list project statuses
    try:
        statuses = IssueStatus.query.filter_by(
            project_id=project_id
        ).order_by(IssueStatus.order_index).all()
        
        return jsonify({
            'success': True,
            'statuses': [{
                'id': status.id,
                'name': status.name,
                'color': status.color,
                'order_index': status.order_index,
                'is_done': status.is_done
            } for status in statuses]
        })
        
    except Exception as e:
        print(f"Error fetching statuses: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch statuses',
            'details': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/timeline")
@login_required
def get_project_timeline(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get activities from last 30 days
        thirty_days_ago = get_sri_lanka_time() - timedelta(days=30)
        
        activities = []
        
        # Get issue activities
        issues = Issue.query.filter_by(project_id=project_id)\
            .filter(Issue.created_at >= thirty_days_ago)\
            .order_by(Issue.created_at.desc()).all()
            
        for issue in issues:
            activities.append({
                'type': 'issue',
                'title': f'New issue created: {issue.summary}',
                'description': issue.description[:100] + '...' if issue.description else '',
                'user': issue.reporter.name,
                'timestamp': issue.created_at.strftime('%Y-%m-%d %H:%M')
            })
        
        # Get task activities through epics and stories
        epic_tasks = Task.query.join(Epic).filter(
            Epic.project_id == project_id,
            Task.created_at >= thirty_days_ago
        ).order_by(Task.created_at.desc()).all()
        
        story_tasks = Task.query.join(Story).join(Epic).filter(
            Epic.project_id == project_id,
            Task.created_at >= thirty_days_ago
        ).order_by(Task.created_at.desc()).all()
        
        # Add epic tasks to activities
        for task in epic_tasks:
            activities.append({
                'type': 'task',
                'title': f'New epic task created: {task.title}',
                'description': task.description[:100] + '...' if task.description else '',
                'user': task.creator.name if task.creator else 'Unknown',
                'timestamp': task.created_at.strftime('%Y-%m-%d %H:%M')
            })
            
        # Add story tasks to activities
        for task in story_tasks:
            activities.append({
                'type': 'task',
                'title': f'New story task created: {task.title}',
                'description': task.description[:100] + '...' if task.description else '',
                'user': task.creator.name if task.creator else 'Unknown',
                'timestamp': task.created_at.strftime('%Y-%m-%d %H:%M')
            })
        
        # Sort activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'data': activities
        })
        
    except Exception as e:
        print(f"Error in get_project_timeline: {str(e)}")
        import traceback
        print(traceback.format_exc())  # Print full stack trace
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/project/<int:project_id>/edit")
@login_required
def project_edit(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        abort(403)
    
    # Get company users for team member selection
    users = User.query.filter_by(company_id=project.company_id).all()
    
    project_members = ProjectMember.query.filter_by(project_id=project_id).all()
    
    # Create a set of reviewer user IDs
    reviewer_ids = {pm.user_id for pm in project_members if pm.is_reviewer}
    
    # For general projects, get categories and statuses
    project_status_ids = []
    all_statuses = []

    if project.project_type == 'general':
        # Get project's categories
        categories = TaskCategory.query.filter_by(project_id=project_id).all()
        project.categories = categories
        
        # Get all task statuses
        all_statuses = TaskStatus.query.all()
        
        # Get project statuses ids
        project_statuses = ProjectTaskStatus.query.filter_by(project_id=project_id).all()
        project_status_ids = [ps.task_status_id for ps in project_statuses]
    
    return render_template(
        'tasks/edit_project.html',
        project=project,
        users=users,
        status_colors=status_colors,
        all_statuses=all_statuses,
        project_status_ids=project_status_ids,
        reviewer_ids=reviewer_ids
    )

@tasks_bp.route("/api/projects/<int:project_id>", methods=['PUT'])
@login_required
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        abort(403)
        flash("You don't have permission to access this project", 'danger')

    
    data = request.json
    print("Received data in update_project:", data)  # Debug log
    
    try:
        # Update basic project fields
        print(f"Updating basic fields for project {project_id}")
        project.name = data.get('name', project.name)
        project.key = data.get('key', project.key)
        project.description = data.get('description', project.description)
        
        # Fix: Convert lead_id to integer if it's a string
        if 'lead_id' in data:
            lead_id = data['lead_id']
            if isinstance(lead_id, str) and lead_id.isdigit():
                project.lead_id = int(lead_id)
            elif isinstance(lead_id, int):
                project.lead_id = lead_id
        
        project.status = data.get('status', project.status)
        project.allow_due_date_assignment = data.get('allow_due_date_assignment', project.allow_due_date_assignment)
        
        # Fix: Handle start_date and end_date
        if 'start_date' in data:
            if data['start_date']:
                project.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            else:
                project.start_date = None
                
        if 'end_date' in data:
            if data['end_date']:
                project.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            else:
                project.end_date = None
        
        # Handle team members and reviewers
        if 'team_members' in data:
            print(f"Team members in request: {data.get('team_members')}")
            print(f"Reviewers in request: {data.get('reviewers')}")
            
            # Get current project members
            current_project_members = ProjectMember.query.filter_by(project_id=project_id).all()
            current_member_map = {pm.user_id: pm for pm in current_project_members}
            
            print(f"Current project members: {[pm.user_id for pm in current_project_members]}")
            print(f"Current reviewers: {[pm.user_id for pm in current_project_members if pm.is_reviewer]}")
            
            # Prepare new team members and reviewers
            team_member_ids = set(data.get('team_members', []))
            reviewer_ids = set(data.get('reviewers', []))
            
            # Track changes
            members_to_add = []
            members_to_delete = []
            members_to_update = []
            
            # Find members to delete
            for current_user_id, current_pm in current_member_map.items():
                if current_user_id not in team_member_ids:
                    members_to_delete.append(current_pm)
            
            # Find members to add or update
            for user_id in team_member_ids:
                is_reviewer = user_id in reviewer_ids
                
                if user_id not in current_member_map:
                    # New member
                    new_pm = ProjectMember(
                        project_id=project_id,
                        user_id=user_id,
                        is_reviewer=is_reviewer
                    )
                    members_to_add.append(new_pm)
                else:
                    # Existing member, check if reviewer status changed
                    current_pm = current_member_map[user_id]
                    if current_pm.is_reviewer != is_reviewer:
                        current_pm.is_reviewer = is_reviewer
                        members_to_update.append(current_pm)
            
            # Delete removed members
            for pm in members_to_delete:
                print(f"Deleting member: {pm.user_id}")
                db.session.delete(pm)
            
            # Add new members
            for pm in members_to_add:
                print(f"Adding member: {pm.user_id}, is_reviewer: {pm.is_reviewer}")
                db.session.add(pm)
            
            # Update existing members' reviewer status
            for pm in members_to_update:
                print(f"Updating member: {pm.user_id}, is_reviewer: {pm.is_reviewer}")
            
            # Only log if there are actual changes
            if members_to_delete or members_to_add or members_to_update:
                print(f"Project Members Update: "
                      f"Delete: {len(members_to_delete)}, "
                      f"Add: {len(members_to_add)}, "
                      f"Update: {len(members_to_update)}")
                      
        # Handle categories (for general projects)
        if project.type.name == 'general' and 'categories' in data:
            categories_data = data['categories']
            
            removed_category_ids = []
            existing_categories = []
            new_categories = []

            # Handle category removals
            if 'remove' in categories_data and categories_data['remove']:
                removed_category_ids = categories_data['remove']
                for cat_id in removed_category_ids:
                    # Find and delete the category
                    category = TaskCategory.query.filter_by(id=cat_id, project_id=project_id).first()
                    if category:
                        print(f"Deleting category: {category.name}")
                        db.session.delete(category)
            
            # Handle updates to existing categories
            if 'existing' in categories_data and categories_data['existing']:
                for category_data in categories_data['existing']:
                    # Skip if it's in the removed list
                    if str(category_data['id']) in removed_category_ids:
                        continue
                        
                    # Find the category - Fix: Convert string ID to int
                    cat_id = int(category_data['id']) if isinstance(category_data['id'], str) else category_data['id']
                    category = TaskCategory.query.get(cat_id)
                    if category and category.project_id == project_id:
                        print(f"Updating category: {category.name} to {category_data['name']}")
                        category.name = category_data['name']
                        category.color = category_data['color']
                        category.sla_hours = category_data['sla_hours']
                        
                        # Fix: Handle category_lead_id conversion
                        if 'category_lead_id' in category_data:
                            lead_id = category_data['category_lead_id']
                            if isinstance(lead_id, str) and lead_id.isdigit():
                                category.category_lead_id = int(lead_id)
                            elif isinstance(lead_id, int):
                                category.category_lead_id = lead_id
                            else:
                                category.category_lead_id = None
                        
                        category.attachment_required = category_data.get('attachment_required', False)
            
            # Handle new categories
            if 'new' in categories_data and categories_data['new']:
                for category_data in categories_data['new']:
                    print(f"Adding new category: {category_data['name']}")
                    
                    # Fix: Handle category_lead_id conversion for new categories
                    category_lead_id = None
                    if 'category_lead_id' in category_data:
                        lead_id = category_data['category_lead_id']
                        if isinstance(lead_id, str) and lead_id.isdigit():
                            category_lead_id = int(lead_id)
                        elif isinstance(lead_id, int):
                            category_lead_id = lead_id
                    
                    category = TaskCategory(
                        name=category_data['name'],
                        color=category_data['color'],
                        project_id=project_id,
                        created_by=current_user.id,
                        category_lead_id=category_lead_id,
                        sla_hours=category_data.get('sla_hours', 24),
                        attachment_required=category_data.get('attachment_required', False),
                        created_at=get_sri_lanka_time()
                    )
                    db.session.add(category)
        
        # Fix: Handle project_status_ids if needed
        if 'project_status_ids' in data:
            print(f"Project status IDs received: {data['project_status_ids']}")
            # Add your logic here to handle project status updates
            # This depends on your ProjectStatus model structure
        
        # Fix: Single commit at the end
        db.session.commit()
        flash("Project updated successfully!", 'success')
        print("Database changes committed successfully")
        
        # Query the updated members to verify the changes
        updated_members = ProjectMember.query.filter_by(project_id=project_id).all()
        print(f"Updated project members: {[pm.user_id for pm in updated_members]}")
        print(f"Updated reviewers: {[pm.user_id for pm in updated_members if pm.is_reviewer]}")
        
        # Additional verification: Print updated project details
        db.session.refresh(project)
        print(f"Updated project details - Name: {project.name}, Key: {project.key}, Description: {project.description}")
        print(f"Lead ID: {project.lead_id}, Status: {project.status}")
        print(f"Start Date: {project.start_date}, End Date: {project.end_date}")
        
        return jsonify({'success': True, 'message': 'Project updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating project: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 400  


@tasks_bp.route("/project/<int:project_id>/manage")
@login_required
def project_manage(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        abort(403)
        
    return render_template(
        'tasks/project_management.html',
        project=project
    )


@tasks_bp.route("/api/projects/<int:project_id>", methods=['DELETE'])
@login_required
def delete_project(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'success': False, 'error': 'Unauthorized action'}), 403
        
        # Begin transaction        
        # 1. Delete task-related records
        if project.project_type == 'general':
            # Get all tasks for this project
            tasks = Task.query.filter_by(project_id=project_id).all()
            
            for task in tasks:
                # Delete task comments
                TaskComment.query.filter_by(task_id=task.id).delete()
                
                # Delete task attachments
                TaskAttachment.query.filter_by(task_id=task.id).delete()
                
                # Delete task time entries
                TimeEntry.query.filter_by(task_id=task.id).delete()
                
                # Delete task watchers
                TaskWatcher.query.filter_by(task_id=task.id).delete()
                
                # Delete task history
                TaskHistory.query.filter_by(task_id=task.id).delete()
            
            Task.query.filter_by(project_id=project_id).delete()

            # Delete project task statuses
            ProjectTaskStatus.query.filter_by(project_id=project_id).delete()
            
            # Delete task categories
            TaskCategory.query.filter_by(project_id=project_id).delete()
            
            # Delete all tasks
        
        # 2. Delete issue-related records
        if project.project_type == 'development' or project.project_type == 'general':
            # Get all issues for this project
            issues = Issue.query.filter_by(project_id=project_id).all()
            
            for issue in issues:
                # Delete issue comments
                IssueComment.query.filter_by(issue_id=issue.id).delete()
                
                # Delete issue attachments
                IssueAttachment.query.filter_by(issue_id=issue.id).delete()
                
                # Delete issue history entries
                IssueHistory.query.filter_by(issue_id=issue.id).delete()
                
                # Delete issue links
                IssueLink.query.filter(
                    (IssueLink.source_issue_id == issue.id) | 
                    (IssueLink.target_issue_id == issue.id)
                ).delete()
            
            # Update any issues that reference this project's issues
            Issue.query.filter(Issue.parent_id.in_([i.id for i in issues])).update({Issue.parent_id: None}, synchronize_session=False)
            Issue.query.filter(Issue.epic_id.in_([i.id for i in issues])).update({Issue.epic_id: None}, synchronize_session=False)
            Issue.query.filter(Issue.story_id.in_([i.id for i in issues])).update({Issue.story_id: None}, synchronize_session=False)
            
            # Delete all issues
            Issue.query.filter_by(project_id=project_id).delete()
            
        # 3. Remove team members association
        project.team.clear()

        
        # 4. Delete project record
        db.session.delete(project)
        
        # Commit all changes
        db.session.commit()
        flash("Project deleted successfully!", 'success')

        
        return jsonify({
            'success': True, 
            'message': f'Project {project.name} and all associated data deleted successfully'
        })
        
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting project: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full stack trace for debugging
        
        return jsonify({
            'success': False, 
            'error': f'Failed to delete project: {str(e)}'
        }), 500



@tasks_bp.route("/api/projects/<int:project_id>")
@login_required
def get_project(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get basic project data
        project_data = {
            'id': project.id,
            'name': project.name,
            'key': project.key,
            'description': project.description,
            'status': project.status,
            'allow_due_date_assignment': project.allow_due_date_assignment,
            'project_type': project.project_type,
            'lead': {
                'id': project.lead.id,
                'name': project.lead.name
            } if project.lead else None,
            'start_date': project.start_date.strftime('%Y-%m-%d') if project.start_date else None,
            'end_date': project.end_date.strftime('%Y-%m-%d') if project.end_date else None
        }
        
        return jsonify(project_data)
        
    except Exception as e:
        print(f"Error getting project: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Helper functions
def calculate_project_completion(project):
    """Calculate project completion percentage based on project type"""
    try:
        if project.type.name == 'development':  # Changed from project.project_type
            # For development projects, use issue completion
            issues = Issue.query.filter_by(project_id=project.id).all()
            if not issues:
                return 0
            
            completed_count = sum(1 for issue in issues if issue.status.is_done)
            return round((completed_count / len(issues)) * 100, 2)
        else:
            # For general projects, use task completion
            tasks = Issue.query.filter(
                Issue.project_id == project.id,
                Issue.issue_type_id.in_([6, 7, 8, 9])  # General task types
            ).all()
            if not tasks:
                return 0
            
            completed_count = sum(1 for task in tasks if task.status.is_done)
            return round((completed_count / len(tasks)) * 100, 2)

    except Exception as e:
        print(f"Error calculating completion: {str(e)}")
        return 0
    
def get_development_project_stats(project):
    """Get statistics for development projects"""
    try:
        return {
            'total_epics': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=1  # Epic
            ).count(),
            'total_stories': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=2  # Story
            ).count(),
            'total_tasks': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=3  # Task
            ).count(),
            'total_subtasks': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=5  # Sub-task
            ).count(),
            'total_bugs': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=4  # Bug
            ).count(),
            'status_distribution': get_development_status_distribution(project),
            'priority_distribution': get_development_priority_distribution(project)
        }
    except Exception as e:
        print(f"Error getting development stats: {str(e)}")
        return {}

def get_recent_issues(project, limit=5):
    """
    Get recent issues for a development project with their status changes
    
    Args:
        project: Project object
        limit: Number of recent issues to return (default 5)
    
    Returns:
        List of recent issues with their details
    """
    try:
        recent_issues = Issue.query.filter_by(project_id=project.id)\
            .order_by(Issue.updated_at.desc())\
            .limit(limit)\
            .all()
            
        issues_data = []
        for issue in recent_issues:
            # Get the latest status change from history
            latest_status_change = IssueHistory.query.filter_by(
                issue_id=issue.id,
                field_name='status'
            ).order_by(IssueHistory.changed_at.desc()).first()
            
            issues_data.append({
                'id': issue.id,
                'key': issue.issue_key,
                'summary': issue.summary,
                'type': issue.type.name,
                'status': issue.status.name,
                'priority': issue.priority.name if issue.priority else None,
                'assignee': issue.assignee.name if issue.assignee else None,
                'updated_at': issue.updated_at,
                'status_changed_at': latest_status_change.changed_at if latest_status_change else None,
                'status_changed_by': latest_status_change.user.name if latest_status_change else None,
                'old_status': latest_status_change.old_value if latest_status_change else None,
                'new_status': latest_status_change.new_value if latest_status_change else None
            })
            
        return issues_data
        
    except Exception as e:
        print(f"Error getting recent issues: {str(e)}")
        return []

def get_general_project_stats(project):
    """Get statistics for general projects"""
    try:
        # Get all tasks counts
        total_tasks = Task.query.filter_by(
            project_id=project.id,
        ).count()
        
        # Get completed tasks (status_id 7 is 'Completed' for general projects)
        total_completed = Task.query.filter_by(
            project_id=project.id,
            status_id=3  # Completed status
        ).count()

        return {
            'total_tasks': total_tasks,
            'total_completed': total_completed,  # Add this
            'total_meetings': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=7  # Meeting
            ).count(),
            'total_milestones': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=8  # Milestone
            ).count(),
            'total_subtasks': Issue.query.filter_by(
                project_id=project.id,
                issue_type_id=9  # General Sub-task
            ).count(),
            'status_distribution': get_general_status_distribution(project),
            'priority_distribution': get_general_priority_distribution(project)
        }
    except Exception as e:
        print(f"Error getting general stats: {str(e)}")
        return {
            'total_tasks': 0,
            'total_completed': 0,  # Add default value
            'total_meetings': 0,
            'total_milestones': 0,
            'total_subtasks': 0,
            'status_distribution': {
                'to_do': 0,
                'in_progress': 0,
                'done': 0
            },
            'priority_distribution': {
                'critical': 0,
                'important': 0,
                'normal': 0,
                'optional': 0
            }
        }

def get_development_priority_distribution(project):
    """
    Get priority distribution for development projects
    Development priorities are: Highest, High, Medium, Low, Lowest (IDs 1-5)
    """
    try:
        return {
            'highest': Issue.query.filter_by(
                project_id=project.id,
                priority_id=1
            ).count(),
            'high': Issue.query.filter_by(
                project_id=project.id,
                priority_id=2
            ).count(),
            'medium': Issue.query.filter_by(
                project_id=project.id,
                priority_id=3
            ).count(),
            'low': Issue.query.filter_by(
                project_id=project.id,
                priority_id=4
            ).count(),
            'lowest': Issue.query.filter_by(
                project_id=project.id,
                priority_id=5
            ).count()
        }
    except Exception as e:
        print(f"Error getting development priority distribution: {str(e)}")
        return {
            'highest': 0,
            'high': 0,
            'medium': 0,
            'low': 0,
            'lowest': 0
        }

def get_general_priority_distribution(project):
    """
    Get priority distribution for general projects
    General priorities are: Critical, Important, Normal, Optional (IDs 6-9)
    """
    try:
        return {
            'critical': Task.query.filter_by(
                project_id=project.id,
                priority_id=1
            ).count(),
            'important': Task.query.filter_by(
                project_id=project.id,
                priority_id=2
            ).count(),
            'normal': Task.query.filter_by(
                project_id=project.id,
                priority_id=3
            ).count(),
            'optional': Task.query.filter_by(
                project_id=project.id,
                priority_id=4
            ).count()
        }
    except Exception as e:
        print(f"Error getting general priority distribution: {str(e)}")
        return {
            'critical': 0,
            'important': 0,
            'normal': 0,
            'optional': 0
        }

def get_development_status_distribution(project):
    """Get status distribution for development projects"""
    return {
        'todo': Issue.query.filter_by(project_id=project.id, status_id=1).count(),
        'in_progress': Issue.query.filter_by(project_id=project.id, status_id=2).count(),
        'review': Issue.query.filter_by(project_id=project.id, status_id=3).count(),
        'done': Issue.query.filter_by(project_id=project.id, status_id=4).count()
    }

def get_general_status_distribution(project):
    """Get status distribution for general projects"""
    return {
        'to_do': Task.query.filter_by(project_id=project.id, status_id=1).count(),
        'in_progress': Task.query.filter_by(project_id=project.id, status_id=2).count(),
        'done': Task.query.filter_by(project_id=project.id, status_id=3).count(),
    }

def get_project_activities(project, limit=10):
    """Get recent project activities with improved readability"""
    try:
        activities = []
        
        # Combine activities from different sources
        # 1. Issue/Task History Entries
        history_entries = IssueHistory.query.join(Issue)\
            .filter(Issue.project_id == project.id)\
            .order_by(IssueHistory.changed_at.desc())\
            .limit(limit).all()
        
        for entry in history_entries:
            # Create a human-readable description of the change
            if entry.changed_at:
                change_description = format_history_change(entry)
                if change_description:
                    activities.append({
                        'type': 'update',
                        'title': f'Updated {entry.issue.type.name}: {entry.issue.issue_key}',
                        'description': change_description,
                        'timestamp': entry.changed_at,
                        'user': entry.user.name if entry.user else 'System'
                    })
        
        # 2. Issue/Task Creation Entries
        created_issues = Issue.query.filter(
            Issue.project_id == project.id,
            Issue.created_at.isnot(None)
        ).order_by(Issue.created_at.desc())\
         .limit(limit).all()
        
        for issue in created_issues:
            activities.append({
                'type': 'create',
                'title': f'New {issue.type.name}: {issue.issue_key}',
                'description': issue.summary,
                'timestamp': issue.created_at,
                'user': issue.reporter.name if issue.reporter else 'System'
            })
        
        # 3. Attachments
        if project.type.name == 'development':
            issue_attachments = IssueAttachment.query.join(Issue)\
                .filter(Issue.project_id == project.id)\
                .order_by(IssueAttachment.uploaded_at.desc())\
                .limit(limit).all()
            
            for attachment in issue_attachments:
                activities.append({
                    'type': 'attachment',
                    'title': f'Attachment added to {attachment.issue.type.name}: {attachment.issue.issue_key}',
                    'description': attachment.file_name,
                    'timestamp': attachment.uploaded_at,
                    'user': attachment.uploader.name if attachment.uploader else 'System'
                })
        
        # Sort and limit activities
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        return activities[:limit]
        
    except Exception as e:
        print(f"Error getting activities: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return []
    
def format_history_change(history_entry):
    """
    Create a human-readable description of a history change
    
    Args:
        history_entry (IssueHistory): The history entry to format
    
    Returns:
        str: A readable description of the change
    """
    field_name = history_entry.field_name
    old_value = history_entry.old_value
    new_value = history_entry.new_value
    
    # Mapping of field names to more readable versions
    field_mapping = {
        'status_id': 'Status',
        'priority_id': 'Priority',
        'assignee_id': 'Assignee',
        'epic_id': 'Epic',
        'story_id': 'Story'
    }
    
    # Lookup readable field name
    readable_field = field_mapping.get(field_name, field_name.replace('_', ' ').title())
    
    # Special handling for some fields
    if field_name == 'status_id':
        try:
            old_status = IssueStatus.query.get(int(old_value)) if old_value else None
            new_status = IssueStatus.query.get(int(new_value)) if new_value else None
            old_value = old_status.name if old_status else 'Unassigned'
            new_value = new_status.name if new_status else 'Unassigned'
        except:
            pass
    
    elif field_name == 'priority_id':
        try:
            old_priority = IssuePriority.query.get(int(old_value)) if old_value else None
            new_priority = IssuePriority.query.get(int(new_value)) if new_value else None
            old_value = old_priority.name if old_priority else 'Unassigned'
            new_value = new_priority.name if new_priority else 'Unassigned'
        except:
            pass
    
    elif field_name == 'assignee_id':
        try:
            old_assignee = User.query.get(int(old_value)) if old_value else None
            new_assignee = User.query.get(int(new_value)) if new_value else None
            old_value = old_assignee.name if old_assignee else 'Unassigned'
            new_value = new_assignee.name if new_assignee else 'Unassigned'
        except:
            pass
    
    # Handle None or empty values
    old_value = old_value if old_value not in [None, 'None', ''] else 'Unassigned'
    new_value = new_value if new_value not in [None, 'None', ''] else 'Unassigned'
    
    # Create the change description
    if old_value != new_value:
        return f"Changed {readable_field} from '{old_value}' to '{new_value}'"
    
    return None

def generate_project_key(project_type):
    # Generate the base key using the existing format
    if len(project_type) < 3:
        # For short project types, just use all letters and pad with X if needed
        base_key = (project_type.upper() + "XXX")[:3]
    else:
        base_key = f"{project_type[:2].upper()}{project_type[-1].upper()}"
    
    # Check if the key already exists in the database
    existing_key = Project.query.filter_by(key=base_key).first()
    
    # If the key is unique, return it
    if not existing_key:
        return base_key
    
    # If the key already exists, add a numeric suffix and increment until we find a unique key
    counter = 1
    while True:
        # Format: base_key + numeric suffix (e.g., DEV1, DEV2, etc.)
        new_key = f"{base_key}{counter}"
        
        # Check if this new key exists
        existing_key = Project.query.filter_by(key=new_key).first()
        
        # If this key doesn't exist, it's unique
        if not existing_key:
            return new_key
        
        # Otherwise, try the next number
        counter += 1

# Additional helper functions
def get_priority_distribution(project):
    return {
        'high': Issue.query.join(IssuePriority).filter(
            Issue.project_id == project.id,
            IssuePriority.name.in_(['Highest', 'High'])
        ).count(),
        'medium': Issue.query.join(IssuePriority).filter(
            Issue.project_id == project.id,
            IssuePriority.name == 'Medium'
        ).count(),
        'low': Issue.query.join(IssuePriority).filter(
            Issue.project_id == project.id,
            IssuePriority.name.in_(['Low', 'Lowest'])
        ).count()
    }

def get_category_stats(project):
    stats = {}
    for category in TaskCategory.query.filter_by(project_id=project.id).all():
        total = Task.query.filter_by(
            project_id=project.id,
            category_id=category.id
        ).count()
        
        completed = Task.query.filter_by(
            project_id=project.id,
            category_id=category.id,
            status='Completed'
        ).count()
        
        stats[category.name] = {
            'total': total,
            'completed': completed,
            'percentage': round((completed / total * 100), 2) if total > 0 else 0
        }
    return stats

def get_upcoming_tasks(project, days=7):
    return Task.query.filter(
        Task.project_id == project.id,
        Task.due_date <= get_sri_lanka_time() + timedelta(days=days),
        Task.due_date >= get_sri_lanka_time(),
        Task.status != 'Completed'
    ).all()

def get_overdue_tasks(project):
    return Task.query.filter(
        Task.project_id == project.id,
        Task.due_date < get_sri_lanka_time(),
        Task.status != 'Completed'
    ).all()


#----------TASKS----------#
@tasks_bp.route("/api/projects/<int:project_id>/tasks", methods=['GET'])
@login_required
def get_project_tasks(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # # Ensure this is a general project
        # if project.type.name != 'general':
        #     return jsonify({
        #         'success': False,
        #         'error': 'Tasks can only be retrieved for general projects'
        #     }), 400
      
        # # Optional: Check if user is part of the project team
        # if not (current_user.assigned_role.role_name == 'admin' or project.lead_id == current_user.id or current_user in project.team):
        #     return jsonify({
        #         'success': False,
        #         'error': 'You are not authorized to view tasks for this project'
        #     }), 403
        
        # Get filter parameters
        search = request.args.get('search', '')
        category_id = request.args.get('category')
        status_id = request.args.get('status')
        assignee_id = request.args.get('assignee')
        
        # Base query for tasks in this project
        query = Task.query.filter(
            Task.project_id == project_id,
            Task.task_type == 'general'
        )
        
        # Apply task visibility based on user role
        if not (current_user.assigned_role.role_name in ['admin', 'user']):
            # If not admin or project lead, show tasks that are:
            # 1. Assigned to current user, OR
            # 2. Have visibility granted to current user in TaskVisibility table
            visibility_tasks = db.session.query(TaskVisibility.task_id).filter(
                TaskVisibility.current_owner_id == current_user.id,
                TaskVisibility.visibility == True
            ).subquery()
            
            query = query.filter(
                or_(
                    Task.assigned_to == current_user.id,
                    Task.created_by == current_user.id,
                    Task.id.in_(visibility_tasks)
                )
            )
        
        # Apply filters
        if search:
            query = query.filter(Task.title.ilike(f'%{search}%'))
        
        if category_id:
            query = query.filter(Task.category_id == category_id)
        
        if status_id:
            query = query.filter(Task.status_id == status_id)
        
        if assignee_id:
            # Only allow filtering by assignee if user is project lead
            if current_user.assigned_role.role_name == 'admin' or project.lead_id == current_user.id:
                query = query.filter(Task.assigned_to == assignee_id)
        
        # Order and get tasks
        tasks = query.order_by(Task.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'tasks': [{
                'id': task.id,
                'task_key': task.task_key,
                'title': task.title,
                'description': task.description,
                'category': {
                    'name': task.category.name if task.category else None,
                    'color': task.category.color if task.category else None
                },
                'status': {
                    'name': task.status.name,
                    'color': task.status.color
                } if task.status else None,
                'assignee': {
                    'id': task.assignee.id,
                    'name': task.assignee.name,
                    'profile_picture_base64': task.assignee.profile_picture_base64
                } if task.assignee else None,
                'priority': {
                    'name': task.priority.name,
                    'color': task.priority.color
                } if task.priority else None,
                'due_date': task.due_date.strftime('%Y-%m-%d %H:%M:%S') if task.due_date else None,
                'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for task in tasks]
        })
        
    except Exception as e:
        print(f"Error fetching tasks: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch tasks',
            'details': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/tasks", methods=['POST'])
@login_required
def create_project_task(project_id):
    try:
        print(f"Received request to create task for project ID: {project_id}")
        
        project = Project.query.get_or_404(project_id)
        print(f"Found project: {project.name} (ID: {project.id})")
        
        # Check if this is a general project
        if project.type.name != 'general':
            print("Project is not of type 'general'.")
            return jsonify({
                'success': False,
                'error': 'Tasks can only be created for general projects'
            }), 400
        
        # Check if request has form data or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Process form data
            title = request.form.get('title')
            description = request.form.get('description', '')
            category_id = request.form.get('category_id')
            assignee_id = request.form.get('assignee_id') or None
            status_id = request.form.get('status_id')
            priority_id = request.form.get('priority_id')
            due_date = request.form.get('due_date')
        else:
            # Process JSON data
            data = request.get_json()
            title = data.get('title')
            description = data.get('description', '')
            category_id = data.get('category_id')
            assignee_id = data.get('assignee_id')
            status_id = data.get('status_id')
            priority_id = data.get('priority_id')
            due_date = data.get('due_date')
        
        # Validate required fields
        if not title:
            return jsonify({
                'success': False,
                'error': 'Title is required'
            }), 400
        
        if not status_id:
            return jsonify({
                'success': False,
                'error': 'Status is required'
            }), 400
        
        # Validate category is from this project
        if category_id:
            print(f"Validating category ID: {category_id}")
            category = TaskCategory.query.filter_by(
                id=category_id, 
                project_id=project_id
            ).first()
            if not category:
                print(f"Invalid category ID: {category_id} for project ID: {project_id}")
                return jsonify({
                    'success': False,
                    'error': 'Invalid category for this project'
                }), 400
        
        # Validate status is from this project
        print(f"Validating status ID: {status_id}")
        status = ProjectTaskStatus.query.filter_by(
            id=status_id, 
        ).first()
        
        if not status:
            print(f"Invalid status ID: {status_id} for project ID: {project_id}")
            return jsonify({
                'success': False,
                'error': 'Invalid status for this project'
            }), 400
        
        # Generate a unique task key
        last_task = Task.query.filter(Task.task_key.like(f"{project.key}-%")).order_by(Task.task_key.desc()).first()

        if last_task:
            # Extract the last 4-digit number and increment it
            last_number = int(last_task.task_key.split('-')[-1])  # Get last digits
            new_number = last_number + 1
        else:
            new_number = 1  # Start from 0001 if no tasks exist

        # Format as 4-digit number
        task_key = f"{project.key}-{new_number:04d}"
        print(f"Generated task key: {task_key}")
        
        # Handle due date calculation
        due_date_obj = None
        if project.allow_due_date_assignment and due_date:
            try:
                due_date_obj = datetime.strptime(due_date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid due date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS'
                    }), 400
        elif not project.allow_due_date_assignment and category and hasattr(category, 'sla_hours') and category.sla_hours:
            # Calculate due date based on SLA hours
            current_time = get_sri_lanka_time()
            sla_hours = category.sla_hours or 24  # Default to 24 if not set
            due_date_obj = current_time + timedelta(hours=sla_hours)  # Keep full datetime
            print(f"Calculated due date using SLA ({sla_hours} hours): {due_date_obj}")
        
        # Create new task in the tasks table
        task = Task(
            task_key=task_key,
            title=title,
            description=description,
            project_id=project_id,
            category_id=category_id,
            assigned_to=assignee_id,
            status_id=status_id,
            priority_id=priority_id,
            due_date=due_date_obj,
            created_by=current_user.id,
            company_id=project.company_id,
            task_type='general'
        )
        
        db.session.add(task)
        db.session.flush()  # Get task ID without committing transaction
        
        # Handle file attachments
        files = request.files.getlist('attachments')
        for file in files:
            if file and file.filename:
                # Create a secure filename to prevent path traversal attacks
                filename = secure_filename(file.filename)
                
                # Create attachment
                attachment = TaskAttachment(
                    task_id=task.id,
                    file_name=filename,
                    file_path='',  # Empty since we're storing binary directly
                    file_data=file.read(),  # Read file data into binary
                    uploaded_by=current_user.id,
                    uploaded_at=get_sri_lanka_time()
                )
                db.session.add(attachment)
        
        task_visibility = TaskVisibility(
            task_id=task.id,
            current_owner_id=assignee_id,
            visibility=True
        )
        db.session.add(task_visibility)

        # Commit everything to the database
        db.session.commit()
        
        print(f"Task created successfully with ID: {task.id} and key: {task.task_key}")
        flash("Task created successfully", 'success')

        
        return jsonify({
            'success': True,
            'message': 'Task created successfully',
            'task_id': task.id,
            'task_key': task.task_key,
            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating task: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to create task',
            'details': str(e)
        }), 500


@tasks_bp.route("/api/tasks/<int:task_id>/attachments", methods=['POST'])
@login_required
def add_task_attachment(task_id):
    try:
        # Get the task and verify access
        task = Task.query.get_or_404(task_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.company_id != current_user.company_id:
            return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
        
        if task.is_reviewed == 1:
            return jsonify({'success': False, 'error': 'This task is locked and cannot be modified.'}), 403
            
        current_status = ProjectTaskStatus.query.get(task.status_id)
        if current_status and current_status.is_done:
            return jsonify({'success': False, 'error': 'This task is already completed. You cannot add attachments to a completed task.'}), 403


        # Check if user is assignee or reviewer
        is_creator = Task.created_by == current_user.id,
        is_assignee = task.assigned_to == current_user.id
        is_reviewer = ProjectMember.query.filter_by(
            project_id=task.project_id,
            user_id=current_user.id,
            is_reviewer=1
        ).first() is not None
            
        # Only admin, project lead, assignee, or reviewer can add attachments
        if (not (current_user.assigned_role.role_name in ['admin', 'user']) and 
            task.project.lead_id != current_user.id and 
            not is_creator and
            not is_assignee and 
            not is_reviewer):
            return jsonify({'success': False, 'error': 'You do not have permission to add attachments to this task.'}), 403
        
        # Check if file is in the request
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'}), 400
            
        file = request.files['file']
        
        # If user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'}), 400
        
        if file:
            # Create a secure filename
            filename = secure_filename(file.filename)
            
            # Create attachment
            attachment = TaskAttachment(
                task_id=task_id,
                file_name=filename,
                file_path='',  # Empty since we're storing binary data
                file_data=file.read(),
                uploaded_by=current_user.id,
                uploaded_at=get_sri_lanka_time()
            )
            
            db.session.add(attachment)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'File uploaded successfully',
                'attachment': {
                    'id': attachment.id,
                    'file_name': attachment.file_name,
                    'uploaded_by': current_user.name,
                    'uploaded_at': attachment.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
                }
            })
    
    except Exception as e:
        db.session.rollback()
        print(f"Error adding attachment: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@tasks_bp.route("/api/tasks/<int:task_id>/attachments/<int:attachment_id>", methods=['DELETE'])
@login_required
def delete_task_attachment(task_id, attachment_id):
    try:
        # Get the task and verify access
        task = Task.query.get_or_404(task_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.company_id != current_user.company_id:
            return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
        
        # Get the attachment
        attachment = TaskAttachment.query.get_or_404(attachment_id)
        
        # Verify the attachment belongs to the task
        if attachment.task_id != task_id:
            return jsonify({'success': False, 'error': 'Attachment does not belong to this task'}), 400
        
        # Delete the attachment
        db.session.delete(attachment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Attachment deleted successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting attachment: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@tasks_bp.route("/download_attachment/<int:attachment_id>")
@login_required
def download_attachment(attachment_id):
    try:
        # Get the attachment
        attachment = TaskAttachment.query.get_or_404(attachment_id)
        
        # Get the task
        task = Task.query.get_or_404(attachment.task_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.company_id != current_user.company_id:
            abort(403)
        
        # Create file-like object from binary data
        file_data = io.BytesIO(attachment.file_data)
        
        # Send the file
        return send_file(
            file_data,
            download_name=attachment.file_name,
            as_attachment=True
        )
    
    except Exception as e:
        print(f"Error downloading attachment: {str(e)}")
        abort(500)
   
# @tasks_bp.route("/api/tasks/<int:task_id>", methods=['PUT'])
# @login_required
# def update_task(task_id):
#     task = Issue.query.get_or_404(task_id)
    
#     # Check permission
#     if current_user.role.role_name != 'admin' and task.project.company_id != current_user.company_id:
#         abort(403)
    
#     data = request.get_json()
    
#     # Track changes
#     changes = {}
    
#     # Update status
#     if 'status_id' in data:
#         status_id = int(data['status_id'])
#         if task.status_id != status_id:
#             changes['status_id'] = {
#                 'old': task.status_id,
#                 'new': status_id
#             }
#             task.status_id = status_id
    
#     # Update priority
#     if 'priority_id' in data:
#         priority_id = int(data['priority_id'])
#         if task.priority_id != priority_id:
#             changes['priority_id'] = {
#                 'old': task.priority_id,
#                 'new': priority_id
#             }
#             task.priority_id = priority_id
    
#     # Update assignee
#     if 'assignee_id' in data:
#         assignee_id = data['assignee_id']
#         if task.assignee_id != assignee_id:
#             changes['assignee_id'] = {
#                 'old': task.assignee_id,
#                 'new': assignee_id
#             }
#             task.assignee_id = assignee_id
    
#     try:
#         # Save updates
#         db.session.commit()
        
#         # Create history entries
#         if changes:
#             for field, change in changes.items():
#                 history = IssueHistory(
#                     issue_id=task.id,
#                     field_name=field,
#                     old_value=str(change['old']) if change['old'] is not None else None,
#                     new_value=str(change['new']) if change['new'] is not None else None,
#                     changed_by=current_user.id
#                 )
#                 db.session.add(history)
            
#             db.session.commit()
        
#         return jsonify({
#             'success': True,
#             'message': 'Task updated successfully',
#             'changes': list(changes.keys())
#         })
    
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({
#             'success': False,
#             'error': str(e)
#         }), 500
    
@tasks_bp.route("/api/tasks/<int:task_id>/comments", methods=['POST'])
@login_required
def add_task_comment(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.company_id != current_user.company_id:
        abort(403)

    if task.is_reviewed == 1:
        return jsonify({'success': False, 'error': 'This task is locked and cannot be modified.'}), 403
        
    # Check if user is assignee or reviewer
    is_creator = Task.created_by == current_user.id,
    is_assignee = task.assigned_to == current_user.id
    is_reviewer = ProjectMember.query.filter_by(
        project_id=task.project_id,
        user_id=current_user.id,
        is_reviewer=1
    ).first() is not None
        
    # Only admin, project lead, assignee, or reviewer can add comments
    if (not (current_user.assigned_role.role_name in ['admin', 'user']) and 
        task.project.lead_id != current_user.id and 
        not is_creator and
        not is_assignee and 
        not is_reviewer):
        return jsonify({'success': False, 'error': 'You do not have permission to add comments to this task.'}), 403


    current_status = ProjectTaskStatus.query.get(task.status_id)
    if current_status and current_status.is_done:
        return jsonify({
            'success': False, 
            'error': 'This task is already completed. You cannot add comments to a completed task.'
        }), 403
    
    data = request.get_json()
    comment_text = data.get('comment')
    
    if not comment_text:
        return jsonify({'success': False, 'error': 'Comment text is required'}), 400
    
    try:
        comment = TaskComment(
            task_id=task_id,
            user_id=current_user.id,
            comment=comment_text,
            created_at=get_sri_lanka_time()
        )
        
        db.session.add(comment)
        db.session.commit()
        
        # Get user name for the response
        user = User.query.get(current_user.id)
        
        return jsonify({
            'success': True,
            'message': 'Comment added successfully',
            'comment': {
                'id': comment.id,
                'comment': comment.comment,
                'user_name': user.name,
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error adding comment: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tasks_bp.route("/project/<int:project_id>/tasks")
@login_required
def project_tasks(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check permission first
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
        abort(403)
    
    # Check if this is a general project 
    if project.type.name != 'general':
        flash('This section is only available for general projects', 'error')
        return redirect(url_for('tasks.projects'))
    
    # Get task categories specific to this project
    categories = TaskCategory.query.filter_by(project_id=project_id).all()
    
    # Get statuses for general projects (project type 2)
    statuses = ProjectTaskStatus.query.filter_by(project_id=project_id).order_by(ProjectTaskStatus.order_index).all()

    # Get priorities for general projects 
    priorities = TaskPriority.query.order_by(TaskPriority.order_index).all()

    
    # Get project members for assignee selection
    project_members = project.team

    return render_template(
        'tasks/project_tasks.html',
        project=project,
        categories=categories,
        statuses=statuses,
        priorities=priorities,
        project_members=project_members
    )

@tasks_bp.route("/task/<int:project_id>/<int:task_id>")  # Changed from /tasks to /task
@login_required
def task_detail(task_id, project_id):
    print(f"DEBUG: Accessing task_detail with task_id={task_id}")
    project = Project.query.get_or_404(project_id)

    # Get the task and verify access
    task = Task.query.get_or_404(task_id)
    print(f"DEBUG: Retrieved task {task}")

    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.project.company_id != current_user.company_id:
        print(f"DEBUG: User {current_user.id} does not have access to task {task_id}")
        abort(403)

    # Fetch statuses related to the task
    statuses = ProjectTaskStatus.query.filter_by(project_id=project_id).order_by(ProjectTaskStatus.order_index).all()
    print(f"DEBUG: Retrieved {len(statuses)} statuses")

    # Fetch priorities related to the task
    priorities = TaskPriority.query.order_by(TaskPriority.order_index).all()
    print(f"DEBUG: Retrieved {len(priorities)} priorities")

    # Get task history
    history = TaskHistory.query.filter_by(
        task_id=task_id
    ).order_by(TaskHistory.changed_at.desc()).all()
    print(f"DEBUG: Retrieved {len(history)} history records")

    # Get task comments
    comments = TaskComment.query.filter_by(
        task_id=task_id
    ).order_by(TaskComment.created_at.desc()).all()
    print(f"DEBUG: Retrieved {len(comments)} comments")

    project_members = project.team


    return render_template(
        'tasks/task_detail.html', 
        task=task,
        statuses=statuses,
        project=project,
        priorities=priorities,
        history=history,
        comments=comments,
        project_members=project_members
    )

@tasks_bp.route("/project/<int:project_id>/tasks/task/<int:task_id>")
@login_required
def project_task_detail(project_id, task_id):
    """Route for viewing task details within project context"""
    # Redirect to the main task detail route
    return redirect(url_for('tasks.task_detail', task_id=task_id))

@tasks_bp.route("/api/projects/<int:project_id>/tasks", methods=['GET', 'POST'])
@login_required
def manage_project_tasks(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check project type
    if project.type.name != 'general':
        return jsonify({
            'success': False,
            'error': 'Tasks can only be managed for general projects'
        }), 400
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validate category is from this project
            category_id = data.get('category_id')
            if category_id:
                category = TaskCategory.query.filter_by(
                    id=category_id, 
                    project_id=project_id
                ).first()
                if not category:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid category for this project'
                    }), 400
            
            # Validate status is from this project
            status_id = data.get('status_id')
            status = ProjectTaskStatus.query.filter_by(
                id=status_id, 
                project_id=project_id
            ).first()
            
            # if not status:
            #     # Get default status for the project
            #     status = IssueStatus.query.filter_by(
            #         project_id=project_id, 
            #         order_index=1  # First status
            #     ).first()
            #     status_id = status.id if status else None
            
            # Create new task/issue
            task = Issue(
                project_id=project_id,
                issue_type_id=6,  # General Task type
                issue_key=f"TASK-{get_sri_lanka_time().strftime('%Y%m%d%H%M%S')}",
                summary=data['title'],
                description=data.get('description'),
                category_id=category_id,
                assignee_id=data.get('assignee_id'),
                status_id=status_id,
                priority_id=data.get('priority_id'),
                due_date=datetime.strptime(data['due_date'], '%Y-%m-%d %H:%M:%S').date() if data.get('due_date') else None,
                reporter_id=current_user.id
            )
            
            db.session.add(task)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Task created successfully',
                'task_id': task.id
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating task: {str(e)}")  # For debugging
            return jsonify({
                'success': False,
                'error': 'Failed to create task',
                'details': str(e)
            }), 500
    
    # GET request - list tasks
    try:
        # Get filter parameters
        search = request.args.get('search', '')
        category_id = request.args.get('category')
        status_id = request.args.get('status')
        assignee_id = request.args.get('assignee')
        
        # Base query for tasks in this project
        query = Issue.query.filter(
            Issue.project_id == project_id,
            Issue.issue_type_id == 6  # General Task type
        )
        
        # Apply filters
        if search:
            query = query.filter(Issue.summary.ilike(f'%{search}%'))
        
        if category_id:
            query = query.filter(Issue.category_id == category_id)
        
        if status_id:
            query = query.filter(Issue.status_id == status_id)
        
        if assignee_id:
            query = query.filter(Issue.assignee_id == assignee_id)
        
        # Order and get tasks
        tasks = query.order_by(Issue.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'tasks': [{
                'id': task.id,
                'title': task.summary,
                'description': task.description,
                'category': {
                    'name': task.category.name if task.category else None,
                    'color': task.category.color if task.category else None
                },
                'status': {
                    'name': task.status.name,
                    'color': task.status.color
                },
                'assignee': task.assignee.name if task.assignee else None,
                'priority': task.priority.name if task.priority else None,
                'due_date': task.due_date.strftime('%Y-%m-%d %H:%M:%S') if task.due_date else None,
                'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for task in tasks]
        })
        
    except Exception as e:
        print(f"Error fetching tasks: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch tasks',
            'details': str(e)
        }), 500
    
@tasks_bp.route("/api/tasks/<int:task_id>", methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_task(task_id):
    try:
        task = Task.query.get_or_404(task_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized access'}), 403

        if request.method == 'GET':
            # For GET requests, we should always allow viewing the task details
            # regardless of completion status

            # Get attachments for this task
            attachments = TaskAttachment.query.filter_by(task_id=task_id).all()
            
            # Return task details with attachments
            return jsonify({
                'id': task.id,
                'task_key': task.task_key,
                'title': task.title,
                'description': task.description,
                'category_id': task.category_id,
                'status_id': task.status_id,
                'priority_id': task.priority_id,
                'assignee_id': task.assigned_to,
                'due_date': task.due_date.strftime('%Y-%m-%d %H:%M:%S') if task.due_date else None,
                'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S') if task.updated_at else None,
                'is_done': task.is_done,  # Add the is_done flag
                'is_reviewed': task.is_reviewed,  # Add the is_reviewed flag
                'status': {
                    'id': task.status.id,
                    'name': task.status.name,
                    'is_done': task.status.is_done if hasattr(task.status, 'is_done') else 0
                } if task.status else None,
                'priority': {
                    'id': task.priority.id,
                    'name': task.priority.name
                } if task.priority else None,
                'category': {
                    'id': task.category.id,
                    'name': task.category.name,
                    'attachment_required': bool(task.category.attachment_required) if task.category.attachment_required is not None else False
                } if task.category else None,
                'assignee': {
                    'id': task.assignee.id,
                    'name': task.assignee.name
                } if task.assignee else None,
                'project': {
                    'id': task.project.id,
                    'name': task.project.name
                },
                'attachments': [{
                    'id': attachment.id,
                    'file_name': attachment.file_name,
                    'uploaded_by': attachment.uploader.name if hasattr(attachment, 'uploader') and attachment.uploader else 'Unknown',
                    'uploaded_at': attachment.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if attachment.uploaded_at else None
                } for attachment in attachments]
            })
        
        if task.is_reviewed == 1:
            return jsonify({'success': False, 'error': 'This task is locked and cannot be modified.'}), 403
            
        # Check if user is assignee or reviewer
        is_creator = Task.created_by == current_user.id,
        is_assignee = task.assigned_to == current_user.id
        is_reviewer = ProjectMember.query.filter_by(
            project_id=task.project_id,
            user_id=current_user.id,
            is_reviewer=1
        ).first() is not None
            
        # Only admin, project lead, assignee, or reviewer can modify tasks
        if (not (current_user.assigned_role.role_name in ['admin', 'user']) and 
            task.project.lead_id != current_user.id and
            not is_creator and 
            not is_assignee and 
            not is_reviewer):
            return jsonify({'success': False, 'error': 'You do not have permission to modify this task.'}), 403

        elif request.method == 'PUT':
            # For PUT methods, check if task is already in a completed status
            current_status = ProjectTaskStatus.query.get(task.status_id) if task.status_id else None
            if (current_status and current_status.is_done) or task.is_done == 1:
                # Check if the user is a reviewer for this project
                is_reviewer = False
                
                try:
                    reviewer = ProjectMember.query.filter_by(
                        project_id=task.project_id,
                        user_id=current_user.id,
                        is_reviewer=1
                    ).first()
                    is_reviewer = reviewer is not None
                except Exception as e:
                    print(f"Error checking reviewer status: {str(e)}")
                
                # Only allow modifications if the user is a reviewer
                if not is_reviewer:
                    return jsonify({
                        'success': False,
                        'error': 'This task is already completed. You cannot modify a completed task.'
                    }), 403
            
            try:
                changes = {}
                has_attachments = False  # Define has_attachments here, outside any conditional blocks
                
                # Check if request is form data or JSON
                if request.content_type and 'multipart/form-data' in request.content_type:
                    # Process form data (including file uploads)
                    
                    # Update fields if they're in the form data
                    if 'title' in request.form and request.form['title'] != task.title:
                        changes['title'] = {'old': task.title, 'new': request.form['title']}
                        task.title = request.form['title']
                        
                    if 'description' in request.form and request.form['description'] != task.description:
                        changes['description'] = {'old': task.description, 'new': request.form['description']}
                        task.description = request.form['description']
                        
                    if 'category_id' in request.form and request.form['category_id'] and int(request.form['category_id']) != task.category_id:
                        changes['category_id'] = {'old': task.category_id, 'new': int(request.form['category_id'])}
                        task.category_id = int(request.form['category_id'])
                        
                    # In the form data processing section:
                    if 'status_id' in request.form and request.form['status_id'] and int(request.form['status_id']) != task.status_id:
                        # Get status to check if it's a completion status
                        new_status_id = int(request.form['status_id'])
                        new_status = ProjectTaskStatus.query.get(new_status_id)
                        if not new_status:
                            return jsonify({'success': False, 'error': 'Invalid status ID'}), 400
                        
                        changes['status_id'] = {'old': task.status_id, 'new': new_status_id}
                        task.status_id = new_status_id
                        
                        # Update is_done based on status
                        old_is_done = task.is_done
                        is_newly_completed = False
                        
                        if new_status.is_done and task.is_done == 0:
                            task.is_done = 1
                            is_newly_completed = True
                            changes['is_done'] = {'old': old_is_done, 'new': 1}
                        elif not new_status.is_done and task.is_done == 1:
                            # Only reset is_done if it was previously set
                            task.is_done = 0
                            changes['is_done'] = {'old': 1, 'new': 0}
                        
                        # If the task is newly marked as completed, give visibility to all reviewers
                        if is_newly_completed:
                            # Get all reviewers for this project
                            reviewers = ProjectMember.query.filter_by(
                                project_id=task.project_id,
                                is_reviewer=1
                            ).all()
                            
                            reviewer_ids = [reviewer.user_id for reviewer in reviewers]
                            
                            # Get existing visibility records for this task
                            existing_visibility = TaskVisibility.query.filter_by(
                                task_id=task.id
                            ).all()
                            
                            # Create a set of user IDs who already have visibility
                            existing_user_ids = {vis.current_owner_id for vis in existing_visibility}
                            
                            # For each reviewer, add visibility if they don't already have it
                            for reviewer_id in reviewer_ids:
                                if reviewer_id not in existing_user_ids:
                                    visibility = TaskVisibility(
                                        task_id=task.id,
                                        current_owner_id=reviewer_id,
                                        visibility=True
                                    )
                                    db.session.add(visibility)
                        
                    if 'priority_id' in request.form and request.form['priority_id'] and int(request.form['priority_id']) != task.priority_id:
                        changes['priority_id'] = {'old': task.priority_id, 'new': int(request.form['priority_id'])}
                        task.priority_id = int(request.form['priority_id'])
                        
                    if 'assignee_id' in request.form:
                        new_assignee = int(request.form['assignee_id']) if request.form['assignee_id'] else None
                        if new_assignee != task.assigned_to:
                            changes['assigned_to'] = {'old': task.assigned_to, 'new': new_assignee}
                            task.assigned_to = new_assignee

                            task_visibility = TaskVisibility(
                                task_id=task.id,
                                current_owner_id=new_assignee,
                                visibility=True
                            )
                            db.session.add(task_visibility)
                            
                    if 'due_date' in request.form and request.form['due_date']:
                        old_date = task.due_date.strftime('%Y-%m-%d %H:%M:%S') if task.due_date else None
                        new_date = request.form['due_date']
                        
                        if old_date != new_date:
                            changes['due_date'] = {'old': old_date, 'new': new_date}
                            try:
                                task.due_date = datetime.strptime(new_date, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                try:
                                    task.due_date = datetime.strptime(new_date, '%Y-%m-%d')
                                except ValueError:
                                    return jsonify({
                                        'success': False,
                                        'error': 'Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS'
                                    }), 400
                    
                    # Handle file attachments
                    files = request.files.getlist('attachments')
                    for file in files:
                        if file and file.filename:
                            has_attachments = True
                            filename = secure_filename(file.filename)
                            
                            # Create attachment
                            attachment = TaskAttachment(
                                task_id=task.id,
                                file_name=filename,
                                file_path='',  # We'll store the binary data directly
                                file_data=file.read(),
                                uploaded_by=current_user.id,
                                uploaded_at=get_sri_lanka_time()
                            )
                            db.session.add(attachment)
                else:
                    # Process JSON data
                    data = request.get_json()
                    if not data:
                        return jsonify({'success': False, 'error': 'No data provided'}), 400
                    
                    # Update fields if they're in the data
                    if 'title' in data and data['title'] != task.title:
                        changes['title'] = {'old': task.title, 'new': data['title']}
                        task.title = data['title']
                        
                    if 'description' in data and data['description'] != task.description:
                        changes['description'] = {'old': task.description, 'new': data['description']}
                        task.description = data['description']
                        
                    if 'category_id' in data and data['category_id'] != task.category_id:
                        changes['category_id'] = {'old': task.category_id, 'new': data['category_id']}
                        task.category_id = data['category_id']
                        
                    # Inside the PUT method of manage_task function:

                    # When handling status_id changes in JSON data:
                    if 'status_id' in data and int(data['status_id']) != task.status_id:
                        # Get status to check if it's a completion status
                        new_status_id = int(data['status_id'])
                        new_status = ProjectTaskStatus.query.get(new_status_id)
                        if not new_status:
                            return jsonify({'success': False, 'error': 'Invalid status ID'}), 400
                        
                        changes['status_id'] = {'old': task.status_id, 'new': new_status_id}
                        task.status_id = new_status_id
                        
                        # Update is_done based on status
                        old_is_done = task.is_done
                        is_newly_completed = False
                        
                        if new_status.is_done and task.is_done == 0:
                            task.is_done = 1
                            is_newly_completed = True
                            changes['is_done'] = {'old': old_is_done, 'new': 1}
                        elif not new_status.is_done and task.is_done == 1:
                            # Only reset is_done if it was previously set
                            task.is_done = 0
                            changes['is_done'] = {'old': 1, 'new': 0}
                        
                        # If the task is newly marked as completed, give visibility to all reviewers
                        if is_newly_completed:
                            # Get all reviewers for this project
                            reviewers = ProjectMember.query.filter_by(
                                project_id=task.project_id,
                                is_reviewer=1
                            ).all()
                            
                            reviewer_ids = [reviewer.user_id for reviewer in reviewers]
                            print(f"Found {len(reviewer_ids)} reviewers for project {task.project_id}: {reviewer_ids}")
                            
                            # Get existing visibility records for this task
                            existing_visibility = TaskVisibility.query.filter_by(
                                task_id=task.id
                            ).all()
                            
                            # Create a set of user IDs who already have visibility
                            existing_user_ids = {vis.current_owner_id for vis in existing_visibility}
                            print(f"Existing visibility permissions for task {task.id}: {existing_user_ids}")
                            
                            # For each reviewer, add visibility if they don't already have it
                            visibility_added_count = 0
                            for reviewer_id in reviewer_ids:
                                if reviewer_id not in existing_user_ids:
                                    print(f"Adding visibility for reviewer {reviewer_id} to task {task.id}")
                                    visibility = TaskVisibility(
                                        task_id=task.id,
                                        current_owner_id=reviewer_id,
                                        visibility=True
                                    )
                                    db.session.add(visibility)
                                    visibility_added_count += 1
                                else:
                                    print(f"Reviewer {reviewer_id} already has visibility for task {task.id}")
                            
                            print(f"Added visibility for {visibility_added_count} new reviewers")
                                            
                    if 'priority_id' in data and int(data['priority_id']) != task.priority_id:
                        changes['priority_id'] = {'old': task.priority_id, 'new': int(data['priority_id'])}
                        task.priority_id = int(data['priority_id'])
                        
                    if 'assignee_id' in data:
                        new_assignee = data['assignee_id'] if data['assignee_id'] else None
                        if new_assignee != task.assigned_to:
                            changes['assigned_to'] = {'old': task.assigned_to, 'new': new_assignee}
                            task.assigned_to = new_assignee

                            task_visibility = TaskVisibility(
                                task_id=task.id,
                                current_owner_id=new_assignee,
                                visibility=True
                            )
                            db.session.add(task_visibility)
                            
                    if 'due_date' in data:
                        old_date = task.due_date.strftime('%Y-%m-%d %H:%M:%S') if task.due_date else None
                        new_date = data['due_date'] if data['due_date'] else None
                        
                        if old_date != new_date:
                            changes['due_date'] = {'old': old_date, 'new': new_date}
                            task.due_date = datetime.strptime(new_date, '%Y-%m-%d %H:%M:%S') if new_date else None

                # If there were changes or new attachments, update the task
                if changes or (request.content_type and 'multipart/form-data' in request.content_type and has_attachments):
                    task.updated_at = get_sri_lanka_time()
                    db.session.commit()
                    
                    # Record all changes in history
                    for field, change in changes.items():
                        history = TaskHistory(
                            task_id=task.id,
                            field_name=field,
                            old_value=str(change['old']) if change['old'] is not None else None,
                            new_value=str(change['new']) if change['new'] is not None else None,
                            changed_by=current_user.id,
                            changed_at=get_sri_lanka_time()
                        )
                        db.session.add(history)
                    
                    if has_attachments:
                        # Add history entry for attachments
                        history = TaskHistory(
                            task_id=task.id,
                            field_name='attachments',
                            old_value='',
                            new_value='New attachments added',
                            changed_by=current_user.id,
                            changed_at=get_sri_lanka_time()
                        )
                        db.session.add(history)
                    
                    db.session.commit()
                    flash("Task updated successfully", 'success')

                    
                    return jsonify({
                        'success': True,
                        'message': 'Task updated successfully',
                        'changes': list(changes.keys()) + (['attachments'] if has_attachments else [])
                    })
                else:
                    return jsonify({
                        'success': True,
                        'message': 'No changes made to task'
                    })
            except Exception as e:
                db.session.rollback()
                print(f"Error updating task: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        elif request.method == 'DELETE':
            # Handle DELETE logic
            try:
                print(f"[Task Delete] Starting deletion process for task_id: {task_id}")
                
                # Delete related data
                TaskComment.query.filter_by(task_id=task_id).delete()
                TaskAttachment.query.filter_by(task_id=task_id).delete()
                TimeEntry.query.filter_by(task_id=task_id).delete()
                TaskWatcher.query.filter_by(task_id=task_id).delete()
                TaskHistory.query.filter_by(task_id=task_id).delete()
                
                # Delete the task itself
                db.session.delete(task)
                db.session.commit()
                flash("Task deleted successfully", 'danger')

                
                return jsonify({
                    'success': True,
                    'message': 'Task deleted successfully'
                })
            except Exception as e:
                db.session.rollback()
                print(f"[Task Delete] ERROR: Failed to delete task {task_id}: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to delete task: {str(e)}'
                }), 500
        
        # Add a catch-all return in case none of the method handlers are triggered
        return jsonify({
            'success': False,
            'error': 'Invalid method or request'
        }), 400
        
    except Exception as e:
        db.session.rollback()
        print(f"Unexpected error in manage_task: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


@tasks_bp.route("/api/tasks/<int:task_id>")
@login_required
def get_task_details(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Check permissions
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.company_id != current_user.company_id:
        abort(403)
    
    # Get attachments for this task
    attachments = TaskAttachment.query.filter_by(task_id=task_id).all()
    
    # Explicitly handle category with attachment_required
    category_data = None
    if task.category:
        # Debugging: Print out raw category details
        print(f"Raw Category Details:")
        print(f"ID: {task.category.id}")
        print(f"Name: {task.category.name}")
        print(f"Project ID: {task.category.project_id}")
        
        # Try to fetch the category directly to double-check
        try:
            direct_category = TaskCategory.query.get(task.category.id)
            print(f"Direct Category Fetch:")
            print(f"Attachment Required (direct): {direct_category.attachment_required}")
        except Exception as e:
            print(f"Error fetching direct category: {str(e)}")
        
        # Prepare category data with explicit boolean conversion
        category_data = {
            'id': task.category.id,
            'name': task.category.name,
            'attachment_required': bool(task.category.attachment_required) if task.category.attachment_required is not None else False
        }
        
        print(f"Prepared Category Data: {category_data}")
    
    return jsonify({
        'id': task.id,
        'task_key': task.task_key,
        'title': task.title,
        'description': task.description,
        'category_id': task.category_id,
        'status_id': task.status_id,
        'priority_id': task.priority_id,
        'assignee_id': task.assigned_to,
        'due_date': task.due_date.strftime('%Y-%m-%d %H:%M:%S') if task.due_date else None,
        'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S') if task.updated_at else None,
        'is_done': task.is_done,
        'is_reviewed': task.is_reviewed,
        'status': {
            'id': task.status.id,
            'name': task.status.name,
            'is_done': task.status.is_done if hasattr(task.status, 'is_done') else 0
        } if task.status else None,
        'priority': {
            'id': task.priority.id,
            'name': task.priority.name
        } if task.priority else None,
        'category': category_data,
        'assignee': {
            'id': task.assignee.id,
            'name': task.assignee.name
        } if task.assignee else None,
        'project': {
            'id': task.project.id,
            'name': task.project.name
        },
        'attachments': [{
            'id': attachment.id,
            'file_name': attachment.file_name,
            'uploaded_by': attachment.uploader.name if hasattr(attachment, 'uploader') and attachment.uploader else 'Unknown',
            'uploaded_at': attachment.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if attachment.uploaded_at else None
        } for attachment in attachments]
    })


@tasks_bp.route("/api/categories/<int:category_id>")
@login_required
def get_category(category_id):
    try:
        category = TaskCategory.query.get_or_404(category_id)
        
        # Check permission
        project = Project.query.get(category.project_id)
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        category_data = {
            'id': category.id,
            'name': category.name,
            'color': category.color,
            'sla_hours': category.sla_hours or 24,  # Default to 24 if not set
            'lead': {
                'id': category.category_lead.id,
                'name': category.category_lead.name
            } if category.category_lead else None
        }
        
        return jsonify({
            'success': True,
            'category': category_data
        })
    except Exception as e:
        print(f"Error getting category: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tasks_bp.route("/api/projects/<int:project_id>/check-reviewer")
@login_required
def check_if_user_is_reviewer(project_id):
    """Check if the current user is a reviewer for this project"""
    try:
        # Check if user is a reviewer for this project
        reviewer = ProjectMember.query.filter_by(
            project_id=project_id,
            user_id=current_user.id,
            is_reviewer=1
        ).first()
        
        return jsonify({
            'success': True,
            'is_reviewer': reviewer is not None
        })
    except Exception as e:
        print(f"Error checking reviewer status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/tasks/<int:task_id>/review-status", methods=['PUT'])
@login_required
def update_review_status(task_id):
    """Update the review status of a task"""
    try:
        # Get the task and verify access
        task = Task.query.get_or_404(task_id)
        
        # Check if user is a reviewer for this project
        reviewer = ProjectMember.query.filter_by(
            project_id=task.project_id,
            user_id=current_user.id,
            is_reviewer=1
        ).first()
        
        if not reviewer:
            return jsonify({'success': False, 'error': 'Only reviewers can update the review status'}), 403
        
        # Get review status from request
        data = request.get_json()
        if not data or 'is_reviewed' not in data:
            return jsonify({'success': False, 'error': 'Review status is required'}), 400
            
        new_review_status = data['is_reviewed']
        old_review_status = task.is_reviewed
        
        # Update the task
        task.is_reviewed = new_review_status
        task.updated_at = get_sri_lanka_time()
        
        # Create history entry
        history = TaskHistory(
            task_id=task.id,
            field_name='is_reviewed',
            old_value=str(old_review_status) if old_review_status is not None else '0',
            new_value=str(new_review_status),
            changed_by=current_user.id,
            changed_at=get_sri_lanka_time()
        )
        
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Review status updated successfully',
            'task': {
                'id': task.id,
                'is_reviewed': task.is_reviewed
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error updating review status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ---------- ISSUES ------------------------------------------- #

@tasks_bp.route("/project/<int:project_id>/issues")
@login_required
def project_issues(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Fetch only the original, unique issue types
    issue_types = IssueType.query.filter(
        IssueType.id.in_([1, 2, 3, 4, 5])  # Epic, Story, Task, Bug, Sub-task
    ).all()
    
    # Fetch only the original, unique statuses
    statuses = IssueStatus.query.filter(
        IssueStatus.id.in_([1, 2, 3, 4])  # To Do, In Progress, Review, Done
    ).order_by(IssueStatus.order_index).all()
    
    # Fetch only the original, unique priorities
    priorities = IssuePriority.query.filter(
        IssuePriority.id.in_([1, 2, 3, 4, 5])  # Highest, High, Medium, Low, Lowest
    ).order_by(IssuePriority.order_index).all()
    
    # Get project members for assignee selection
    project_members = project.team
    
    return render_template(
        'tasks/project_issues.html',
        project=project,
        issue_types=issue_types,
        statuses=statuses,
        priorities=priorities,
        project_members=project_members
    )


@tasks_bp.route("/api/projects/<int:project_id>/issues", methods=['GET', 'POST'])
@login_required
def manage_issues(project_id):
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        try:
            last_task = Issue.query.filter(Issue.issue_key.like(f"{project.key}-%")).order_by(Issue.issue_key.desc()).first()

            if last_task:
                # Extract the last 4-digit number and increment it
                last_number = int(last_task.issue_key.split('-')[-1])  # Get last digits
                new_number = last_number + 1
            else:
                new_number = 1  # Start from 0001 if no tasks exist

            # Format as 4-digit number
            issue_key = f"{project.key}-{new_number:04d}"
            print(f"Generated task key: {issue_key}")  # Debug log

            # Get form data
            issue_type_id = int(request.form['issue_type_id'])
            
            # Create base issue object
            issue = Issue(
                project_id=project_id,
                issue_type_id=issue_type_id,
                issue_key=issue_key,
                summary=request.form['summary'],
                description=request.form.get('description'),
                reporter_id=current_user.id,
                status_id=request.form.get('status_id'),
                priority_id=request.form.get('priority_id'),
                assignee_id=request.form.get('assignee_id') or None,
                due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form.get('due_date') else None
            )
            
            # Set relationship fields based on issue type
            if issue_type_id == 2:  # Story
                issue.epic_id = request.form.get('epic_id') or None
                issue.story_points = request.form.get('story_points')
                
            elif issue_type_id == 3:  # Task
                issue.epic_id = request.form.get('epic_id') or None
                issue.story_id = request.form.get('story_id') or None
                issue.original_estimate = request.form.get('original_estimate')
                
            elif issue_type_id == 4:  # Bug
                # For bugs, we need to determine the correct parent references
                if request.form.get('parent_type') == 'story':
                    issue.story_id = request.form.get('parent_id')
                    # If the story has an epic, also link the bug to that epic
                    if request.form.get('epic_id'):
                        issue.epic_id = request.form.get('epic_id')
                elif request.form.get('parent_type') == 'task':
                    issue.parent_id = request.form.get('parent_id')
                    # If the task has a story/epic, also link the bug
                    parent_task = Issue.query.get(request.form.get('parent_id'))
                    if parent_task and parent_task.story_id:
                        issue.story_id = parent_task.story_id
                    if parent_task and parent_task.epic_id:
                        issue.epic_id = parent_task.epic_id
                elif request.form.get('parent_type') == 'epic':
                    issue.epic_id = request.form.get('parent_id')
                
            elif issue_type_id == 5:  # Subtask
                issue.parent_id = request.form.get('parent_id')
                # Also set higher level references
                parent_issue = Issue.query.get(request.form.get('parent_id'))
                if parent_issue:
                    issue.story_id = parent_issue.story_id
                    issue.epic_id = parent_issue.epic_id
            
            # Validate relationships
            errors = issue.validate_relationships()
            if errors:
                return jsonify({'success': False, 'errors': errors}), 400
                
            # Save the issue
            db.session.add(issue)
            db.session.commit()
            
            
            # Create history entry
            history = IssueHistory(
                issue_id=issue.id,
                field_name='status',
                new_value='Created',
                changed_by=current_user.id
            )
            db.session.add(history)
            
            # Handle file attachments
            for key in request.files:
                file = request.files[key]
                if file and file.filename:
                    attachment = IssueAttachment(
                        issue_id=issue.id,
                        file_name=file.filename,
                        file_data=file.read(),
                        file_type=file.content_type,
                        uploaded_by=current_user.id
                    )
                    db.session.add(attachment)
            
            # Finally commit everything
            db.session.commit()
            return jsonify({'success': True, 'message': 'Issue created successfully'})
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating issue: {str(e)}")  # For debugging
            return jsonify({'success': False, 'error': str(e)}), 400
            
    # GET request
    # Get type filter
    issue_type = request.args.get('type')
    status = request.args.get('status')
    assignee = request.args.get('assignee')  # Add this line
    search = request.args.get('search')
    
    query = Issue.query.filter_by(project_id=project_id)
    
    if issue_type:
        query = query.filter_by(issue_type_id=issue_type)
    if status:
        query = query.filter_by(status_id=status)
    if assignee:  # Add this block
        query = query.filter_by(assignee_id=assignee)
    if search:    # Add this block if you want search
        query = query.filter(Issue.summary.ilike(f'%{search}%'))
        
    issues = query.order_by(Issue.created_at.desc()).all()
    
    return jsonify({
        'issues': [{
            'id': issue.id,
            'key': issue.issue_key,
            'type': issue.type.name,
            'summary': issue.summary,
            'status': issue.status.name,
            'priority': issue.priority.name if issue.priority else None,
            'assignee': {
                'id': issue.assignee.id,
                'name': issue.assignee.name,
                'profile_picture_base64': issue.assignee.profile_picture_base64
            } if issue.assignee else None,
            'created_at': issue.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'due_date': issue.due_date.strftime('%Y-%m-%d') if issue.due_date else None,
            'epic': issue.epic.summary if issue.epic else None,
            'parent': issue.parent.summary if issue.parent else None,
            'progress': calculate_issue_progress(issue)
        } for issue in issues]
    })


# @tasks_bp.route("/api/issues/<int:issue_id>", methods=['GET', 'PUT', 'DELETE'])
# @login_required
# def manage_issue(issue_id):
#     issue = Issue.query.get_or_404(issue_id)
    
#     # Check permission
#     if current_user.role.role_name != 'admin' and issue.project.company_id != current_user.company_id:
#         return jsonify({'error': 'Unauthorized'}), 403

        
#     elif request.method == 'PUT':
#         try:
#             data = request.get_json()
            
#             # Update fields
#             if 'status_id' in data:
#                 issue.status_id = data['status_id']
#             if 'priority_id' in data:
#                 issue.priority_id = data['priority_id']
#             if 'assignee_id' in data:
#                 issue.assignee_id = data['assignee_id']
            
#             issue.updated_at = get_sri_lanka_time()
            
#             # Create history entries
#             if 'status_id' in data:
#                 history = IssueHistory(
#                     issue_id=issue.id,
#                     field_name='status_id',
#                     old_value=str(issue.status_id),
#                     new_value=str(data['status_id']),
#                     changed_by=current_user.id,
#                     changed_at=get_sri_lanka_time()
#                 )
#                 db.session.add(history)
                
#             if 'priority_id' in data:
#                 history = IssueHistory(
#                     issue_id=issue.id,
#                     field_name='priority_id',
#                     old_value=str(issue.priority_id),
#                     new_value=str(data['priority_id']),
#                     changed_by=current_user.id,
#                     changed_at=get_sri_lanka_time()
#                 )
#                 db.session.add(history)
                
#             if 'assignee_id' in data:
#                 history = IssueHistory(
#                     issue_id=issue.id,
#                     field_name='assignee_id',
#                     old_value=str(issue.assignee_id) if issue.assignee_id else 'None',
#                     new_value=str(data['assignee_id']) if data['assignee_id'] else 'None',
#                     changed_by=current_user.id,
#                     changed_at=get_sri_lanka_time()
#                 )
#                 db.session.add(history)
            
#             db.session.commit()
            
#             return jsonify({
#                 'success': True,
#                 'message': 'Issue updated successfully'
#             })
#         except Exception as e:
#             db.session.rollback()
#             return jsonify({
#                 'success': False,
#                 'error': str(e)
#             }), 500

# Single issue management
@tasks_bp.route("/api/projects/<int:project_id>/issues", methods=['GET'])
@login_required
def get_project_issues(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # Optional: Check if user is part of the project team
        if not (current_user.assigned_role.role_name == 'admin' or project.lead_id == current_user.id or current_user in project.team):
            return jsonify({
                'success': False,
                'error': 'You are not authorized to view tasks for this project'
            }), 403
        
        # Get filter parameters
        search = request.args.get('search', '')
        category_id = request.args.get('category')
        status_id = request.args.get('status')
        assignee_id = request.args.get('assignee')
        type_id = request.args.get('type')
        
        # Base query for issues in this project
        query = Issue.query.filter(
            Issue.project_id == project_id
        )
        
        # Apply issue visibility based on user role
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.lead_id != current_user.id:
            # If not project lead, only show issues assigned to current user or reported by current user
            query = query.filter(
                (Issue.assignee_id == current_user.id) | 
                (Issue.reporter_id == current_user.id)
            )
        
        # Apply filters
        if search:
            query = query.filter(Issue.summary.ilike(f'%{search}%'))
        
        if category_id:
            query = query.filter(Issue.category_id == category_id)
        
        if status_id:
            query = query.filter(Issue.status_id == status_id)
        
        if assignee_id:
            # Only allow filtering by assignee if user is project lead
            if current_user.assigned_role.role_name == 'admin' or project.lead_id == current_user.id:
                query = query.filter(Issue.assignee_id == assignee_id)
        
        if type_id:
            query = query.filter(Issue.issue_type_id == type_id)
        
        # Order and get issues
        issues = query.order_by(Issue.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'issues': [{
                'id': issue.id,
                'issue_key': issue.issue_key,
                'summary': issue.summary,
                'description': issue.description,
                'type': {
                    'id': issue.type.id,
                    'name': issue.type.name
                } if issue.type else None,
                'category': {
                    'id': issue.category.id,
                    'name': issue.category.name,
                    'color': issue.category.color
                } if issue.category else None,
                'status': {
                    'id': issue.status.id,
                    'name': issue.status.name,
                    'color': issue.status.color
                } if issue.status else None,
                'priority': {
                    'id': issue.priority.id,
                    'name': issue.priority.name,
                    'color': issue.priority.color
                } if issue.priority else None,
                'assignee': {
                    'id': issue.assignee.id,
                    'name': issue.assignee.name
                } if issue.assignee else None,
                'reporter': {
                    'id': issue.reporter.id,
                    'name': issue.reporter.name
                },
                'due_date': issue.due_date.strftime('%Y-%m-%d') if issue.due_date else None,
                'story_points': issue.story_points,
                'created_at': issue.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for issue in issues]
        })
        
    except Exception as e:
        print(f"Error fetching issues: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch issues',
            'details': str(e)
        }), 500



@tasks_bp.route("/issues/<int:issue_id>")
@login_required 
def issue_detail(issue_id):
    issue = Issue.query.get_or_404(issue_id)
    
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
        abort(403)
    
    # Get statuses based on project type
    if issue.project.type.name == 'development':
        statuses = IssueStatus.query.filter(
            IssueStatus.id.in_([1, 2, 3, 4])  # Development statuses
        ).order_by(IssueStatus.order_index).all()
    else:
        statuses = IssueStatus.query.filter(
            IssueStatus.id.in_([5, 6, 7])  # General statuses
        ).order_by(IssueStatus.order_index).all()
    
    # Get priorities based on project type
    priorities = IssuePriority.query.filter_by(
        project_type_id=issue.project.type.id
    ).order_by(IssuePriority.order_index).all()
    
    history = IssueHistory.query.filter_by(issue_id=issue_id).order_by(IssueHistory.changed_at.desc()).all()
    comments = IssueComment.query.filter_by(issue_id=issue_id).order_by(IssueComment.created_at.desc()).all()
    
    # Get allowed child types
    allowed_child_types = get_allowed_child_types(issue.issue_type_id)

    return render_template(
        'tasks/issue_detail.html',
        issue=issue,
        project=issue.project,
        statuses=statuses,
        priorities=priorities,
        project_members=issue.project.team,
        history=history,
        comments=comments,
        allowed_child_types=allowed_child_types  # Add this line
    )
    

@tasks_bp.route("/api/issues/<int:issue_id>/comments", methods=['POST'])
@login_required
def add_issue_comment(issue_id):
    issue = Issue.query.get_or_404(issue_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
        abort(403)
    
    data = request.get_json()
    comment_text = data.get('comment')
    
    if not comment_text:
        return jsonify({'success': False, 'error': 'Comment text is required'}), 400
    
    try:
        comment = IssueComment(
            issue_id=issue_id,
            comment=comment_text,
            created_by=current_user.id,
            created_at=get_sri_lanka_time()
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment added successfully',
            'comment': {
                'id': comment.id,
                'comment': comment.comment,
                'created_by': comment.author.name,  # Using the relationship to get author name
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error adding issue comment: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@tasks_bp.route("/download_issue_attachment/<int:attachment_id>")
@login_required
def download_issue_attachment(attachment_id):
    try:
        # Get the attachment
        attachment = IssueAttachment.query.get_or_404(attachment_id)
        
        # Get the issue
        issue = Issue.query.get_or_404(attachment.issue_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
            abort(403)
        
        # Create file-like object from binary data
        file_data = io.BytesIO(attachment.file_data)
        
        # Send the file
        return send_file(
            file_data,
            download_name=attachment.file_name,
            as_attachment=True
        )
    
    except Exception as e:
        print(f"Error downloading issue attachment: {str(e)}")
        abort(500)

@tasks_bp.route("/api/issues/<int:issue_id>", methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_issue(issue_id):
    issue = Issue.query.get_or_404(issue_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'issue': {
                'id': issue.id,
                'type': {
                    'id': issue.type.id,
                    'name': issue.type.name
                },
                'summary': issue.summary,
                'description': issue.description,
                'status': {
                    'id': issue.status.id,
                    'name': issue.status.name
                },
                'priority': {
                    'id': issue.priority.id,
                    'name': issue.priority.name
                } if issue.priority else None,
                'assignee': {
                    'id': issue.assignee.id,
                    'name': issue.assignee.name
                } if issue.assignee else None,
                'epic_id': issue.epic_id,
                'story_id': issue.story_id,
                'due_date': issue.due_date.strftime('%Y-%m-%d') if issue.due_date else None
            }
        })
    
    elif request.method == 'DELETE':
        try:
            # Delete related records first
            IssueComment.query.filter_by(issue_id=issue_id).delete()
            IssueHistory.query.filter_by(issue_id=issue_id).delete()
            IssueAttachment.query.filter_by(issue_id=issue_id).delete()
            
            # Delete the issue
            db.session.delete(issue)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Issue deleted successfully'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            
            # Update fields
            if 'summary' in data:
                issue.summary = data['summary']
            if 'description' in data:
                issue.description = data['description']
            if 'status_id' in data:
                issue.status_id = data['status_id']
            if 'priority_id' in data:
                issue.priority_id = data['priority_id']
            if 'assignee_id' in data:
                issue.assignee_id = data['assignee_id']
            if 'due_date' in data:
                issue.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d') if data['due_date'] else None
                
            issue.updated_at = get_sri_lanka_time()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Issue updated successfully'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

def get_allowed_child_types(parent_type_id):
    """Get allowed child issue types for a parent issue type"""
    constraints = IssueTypeConstraint.query.filter_by(parent_type_id=parent_type_id).all()
    return [constraint.child_type_id for constraint in constraints]

@tasks_bp.route("/api/issues/<int:issue_id>")
@login_required
def get_issue_detail(issue_id):
    issue = Issue.query.get_or_404(issue_id)
    
    # Check permission
    if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Get the issue context
    issue_context = {
        'epic': issue.epic.to_dict() if issue.epic else None,
        'story': issue.story.to_dict() if issue.story else None,
        'parent': issue.parent.to_dict() if issue.parent else None,
        'subtasks': [subtask.to_dict() for subtask in issue.subtasks],
        'related_bugs': [bug.to_dict() for bug in Issue.query.filter_by(
            parent_id=issue.id, 
            issue_type_id=4  # Bug type
        ).all()]
    }
    
    
    return jsonify({
        'success': True,
        'issue': issue.to_dict(),
        'context': issue_context,
        'allowed_actions': {
            'can_create_subtask': issue.issue_type_id in [2, 3, 4],  # Story, Task, Bug
            'can_link_bug': issue.issue_type_id != 4  # All except Bug
        }
    })



# Helper function for calculating issue progress
def calculate_issue_progress(issue):
    """Calculate progress percentage for an issue based on its type and status"""
    if issue.type.name == 'Epic':
        # Calculate progress based on child issues
        children = Issue.query.filter_by(epic_id=issue.id).all()
        if not children:
            return 0
        completed = len([c for c in children if c.status.is_done])
        return int((completed / len(children)) * 100)
    else:
        # Return progress based on status
        statuses = IssueStatus.query.order_by(IssueStatus.order_index).all()
        current_status_index = next((i for i, s in enumerate(statuses) if s.id == issue.status_id), 0)
        return int((current_status_index / (len(statuses) - 1)) * 100)
    
@tasks_bp.route("/api/epics/<int:epic_id>/stories")
@login_required
def get_epic_stories(epic_id):
    # Get all issues that are stories (type_id=2) under this epic
    stories = Issue.query.filter_by(
        epic_id=epic_id,
        issue_type_id=2  # Assuming 2 is the ID for Story type
    ).all()
    
    return jsonify({
        'stories': [{
            'id': story.id,
            'summary': story.summary,
            'status': story.status.name
        } for story in stories]
    })

@tasks_bp.route("/api/stories/<int:story_id>/tasks")
@login_required
def get_story_tasks(story_id):
    try:
        # First verify the story exists and user has access
        story = Issue.query.filter_by(
            id=story_id, 
            issue_type_id=2  # Story type
        ).first_or_404()
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and story.project.company_id != current_user.company_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Get tasks where parent_id is this story's ID
        tasks = Issue.query.filter(
            Issue.epic_id == story.epic_id,  # Tasks under same epic
            Issue.issue_type_id == 3  # Task type
        ).all()
        
        return jsonify({
            'success': True,
            'tasks': [{
                'id': task.id,
                'summary': task.summary,
                'status': task.status.name
            } for task in tasks]
        })
        
    except Exception as e:
        print(f"Error in get_story_tasks: {str(e)}")  # For debugging
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
@tasks_bp.route("/api/projects/<int:project_id>/all_tasks")
@login_required
def get_all_project_tasks(project_id):
    try:
        # Check project permissions
        project = Project.query.get_or_404(project_id)
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        # Get all tasks (issue_type_id=3) for this project
        tasks = Issue.query.filter_by(
            project_id=project_id,
            issue_type_id=3  # Task type
        ).all()
        
        return jsonify({
            'success': True,
            'tasks': [{
                'id': task.id,
                'summary': task.summary,
                'key': task.issue_key,
                'status': task.status.name if task.status else "Unknown"
            } for task in tasks]
        })
        
    except Exception as e:
        print(f"Error fetching all tasks: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        

# ------------------------------------------------------------------------------ #
# List View
# Add to your routes.py file in the tasks_list_view function

# Replace this part in your tasks_list_view function

@tasks_bp.route("/tasks_list_view")
@login_required
def tasks_list_view():
    try:
        print(f"Current user: {current_user.id}, Role: {current_user.assigned_role.role_name}, Company: {current_user.company_id}")
        
        # Base query with explicit joins
        query = Task.query\
            .join(TaskPriority, Task.priority_id == TaskPriority.id)\
            .join(ProjectTaskStatus, Task.status_id == ProjectTaskStatus.id)
        
        print("Initial query created")
        
        # Get task visibility records for current user - more reliable query
        visible_task_ids = []
        try:
            visibility_records = TaskVisibility.query.filter_by(
                current_owner_id=current_user.id,
                visibility=True
            ).all()
            
            visible_task_ids = [record.task_id for record in visibility_records]
            print(f"Found {len(visible_task_ids)} tasks with visibility for user {current_user.id}")
        except Exception as e:
            print(f"Error getting visibility data: {str(e)}")
            visible_task_ids = []
        
        # Get projects where current user is a reviewer
        reviewer_project_ids = []
        try:
            reviewer_memberships = ProjectMember.query.filter_by(
                user_id=current_user.id,
                is_reviewer=1
            ).all()
            
            reviewer_project_ids = [membership.project_id for membership in reviewer_memberships]
            print(f"User is reviewer for {len(reviewer_project_ids)} projects: {reviewer_project_ids}")
        except Exception as e:
            print(f"Error getting reviewer data: {str(e)}")
            reviewer_project_ids = []
        
        # If not admin, filter by assigned_to or reviewer access or explicit visibility
        if current_user.assigned_role.role_name not in ['super_admin', 'user']:
            # Use the reviewer_project_ids directly in the query
            query = query.filter(
                or_(
                    Task.assigned_to == current_user.id,
                    Task.created_by == current_user.id,
                    # Include tasks that are done and belong to projects where user is reviewer
                    and_(
                        Task.is_done == 1,
                        Task.project_id.in_(reviewer_project_ids) if reviewer_project_ids else False
                    ),
                    # Using a subquery to check visibility
                    Task.id.in_(visible_task_ids) if visible_task_ids else False
                )
            )
        
        # Execute the query
        tasks = query.order_by(Task.created_at.desc()).all()
        print(f"Retrieved {len(tasks)} tasks")
        
        # Create a dictionary mapping task IDs to reviewer status
        is_reviewer_map = {}
        for task in tasks:
            is_reviewer_map[task.id] = task.project_id in reviewer_project_ids
        
        # Calculate statistics
        total_tasks = len(tasks)
        pending_tasks = sum(1 for task in tasks if task.status.task_status_id in [1, 2])
        completed_tasks = sum(1 for task in tasks if task.status.task_status_id == 3)
        deleted_tasks = 0
        
        # Calculate percentages
        pending_percentage = (pending_tasks / total_tasks * 100) if total_tasks > 0 else 0
        completed_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        deleted_percentage = (deleted_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Get all projects for the dropdown in the task creation form
        projects = Project.query.filter_by(company_id=current_user.company_id, project_type_id=2).all()

        return render_template('tasks/tasks_list_view.html',
                             tasks=tasks,
                             projects=projects,
                             total_tasks=total_tasks,
                             pending_tasks=pending_tasks,
                             completed_tasks=completed_tasks,
                             deleted_tasks=deleted_tasks,
                             pending_percentage=pending_percentage,
                             completed_percentage=completed_percentage,
                             deleted_percentage=deleted_percentage,
                             visible_task_ids=visible_task_ids,
                             is_reviewer_map=is_reviewer_map)
                             
    except Exception as e:
        print(f"Error in tasks_list_view: {str(e)}")
        import traceback
        print(traceback.format_exc())  # Print full stack trace
        flash('Error loading tasks', 'error')
        return redirect(url_for('tasks.projects'))

@tasks_bp.route("/api/projects/<int:project_id>/form-data")
@login_required
def get_project_form_data(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get categories for this project
        categories = TaskCategory.query.filter_by(project_id=project_id).all()
        
        # Get statuses for this project
        statuses = ProjectTaskStatus.query.filter_by(project_id=project_id).order_by(ProjectTaskStatus.order_index).all()
        
        # Get all task priorities (not filtered)
        priorities = TaskPriority.query.order_by(TaskPriority.order_index).all()
        
        # Get project team members
        team_members = project.team
        
        return jsonify({
            'success': True,
            'data': {
                'categories': [{
                    'id': category.id,
                    'name': category.name,
                    'color': category.color,
                    'sla_hours': category.sla_hours,
                    'category_lead': {
                        'id': category.category_lead.id,
                        'name': category.category_lead.name
                    } if category.category_lead else None
                } for category in categories],
                'statuses': [{
                    'id': status.id,
                    'name': status.name,
                    'color': status.color,
                    'task_status_id': status.task_status_id,
                    'order_index': status.order_index,
                    'is_done': status.is_done
                } for status in statuses],
                'priorities': [{
                    'id': priority.id,
                    'name': priority.name,
                    'color': priority.color,
                    'order_index': priority.order_index
                } for priority in priorities],
                'team_members': [{
                    'id': member.id,
                    'name': member.name,
                    'email': member.email,
                    'profile_picture': member.profile_picture_base64 if member.profile_picture else None
                } for member in team_members]
            }
        })
        
    except Exception as e:
        print(f"Error fetching project form data: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch project data',
            'details': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/create-task", methods=['POST'])
@login_required
def create_project_task_in_list_view(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check if this is a general project
        if project.type.name != 'general':
            return jsonify({
                'success': False,
                'error': 'Tasks can only be created for general projects'
            }), 400
        
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        assignee_id = request.form.get('assignee_id')
        status_id = request.form.get('status_id')
        priority_id = request.form.get('priority_id')
        due_date = request.form.get('due_date')
        ship_doc_entry_id = request.form.get('order_id')
        
        # Validate required fields
        if not title:
            return jsonify({
                'success': False,
                'error': 'Title is required'
            }), 400
        
        if not status_id:
            return jsonify({
                'success': False,
                'error': 'Status is required'
            }), 400
            
        # Generate task key
        last_task = Task.query.filter(
            Task.task_key.like(f"{project.key}-%")
        ).order_by(Task.task_key.desc()).first()

        if last_task:
            last_number = int(last_task.task_key.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1

        task_key = f"{project.key}-{new_number:04d}"
        
        # Handle due date
        due_date_obj = None
        if due_date:
            try:
                due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid due date format'
                }), 400
                
        # Create the task
        task = Task(
            task_key=task_key,
            title=title,
            description=description,
            project_id=project_id,
            category_id=category_id,
            assigned_to=assignee_id,
            status_id=status_id,
            priority_id=priority_id,
            due_date=due_date_obj,
            created_by=current_user.id,
            company_id=project.company_id,
            task_type='general',
            shipment_id=ship_doc_entry_id if ship_doc_entry_id else None
        )
        
        db.session.add(task)
        db.session.flush()

        task_visibility = TaskVisibility(
            task_id=task.id,
            current_owner_id=assignee_id,
            visibility=True
        )
        db.session.add(task_visibility)
        
        # Handle file attachments
        files = request.files.getlist('attachments')
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                attachment = TaskAttachment(
                    task_id=task.id,
                    file_name=filename,
                    file_path='',
                    file_data=file.read(),
                    uploaded_by=current_user.id,
                    uploaded_at=get_sri_lanka_time()
                )
                db.session.add(attachment)
        
        # Create task history entry
        history = TaskHistory(
            task_id=task.id,
            field_name='status',
            new_value='Created',
            changed_by=current_user.id,
            changed_at=get_sri_lanka_time()
        )
        db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Task created successfully',
            'task': {
                'id': task.id,
                'key': task.task_key
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating task: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tasks_bp.route("/api/projects/<int:project_id>/statuses")
@login_required
def get_all_statuses(project_id):
    try:
        # Query all unique statuses
        statuses = []
        
        # For general projects (using ProjectTaskStatus)
        if project_id > 0:
            status_rows = ProjectTaskStatus.query.filter_by(project_id=project_id).order_by(ProjectTaskStatus.order_index).all()
            statuses = [{
                'id': status.id,
                'name': status.name,
                'color': status.color,
                'order_index': status.order_index
            } for status in status_rows]
        else:
            # Get global statuses from TaskStatus
            status_rows = TaskStatus.query.order_by(TaskStatus.order_index).all()
            statuses = [{
                'id': status.id,
                'name': status.name,
                'color': status.color,
                'order_index': status.order_index
            } for status in status_rows]
        
        return jsonify({
            'success': True,
            'statuses': statuses
        })
    except Exception as e:
        print(f"Error fetching statuses: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ---------------------KANBAN BOARD -------------------- #

@tasks_bp.route("/kanban_board")
@login_required
def tasks_kanban_board():
    if current_user.assigned_role.role_name == 'admin':
        # Admin sees all non-archived projects
        projects = Project.query.filter_by(is_archived=False).all()
    else:
        # Get user's associated companies
        user_companies = [current_user.company_id] + [
            uc.company_id for uc in UserCompany.query.filter_by(user_id=current_user.id).all()
        ]
        
        # Non-admin users see projects from their primary and additional companies
        projects = Project.query.filter(
            Project.company_id.in_(user_companies),
            Project.is_archived == False
        ).all()
    
    return render_template('tasks/tasks_kanban.html', 
                           projects=projects)

@tasks_bp.route("/api/projects/<int:project_id>/kanban")
@login_required
def get_project_kanban_data(project_id):
    try:
        print(f"Fetching Kanban data for project {project_id}")
        
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            print(f"Unauthorized access to project {project_id}")
            return jsonify({'error': 'Unauthorized access'}), 403
        
        # Get project team members for assignee data
        team_members = [
            {
                'id': member.id,
                'name': member.name,
                'email': member.email,
                'profile_picture_base64': member.profile_picture_base64
            } for member in project.team
        ]
        
        # Get priorities with error handling based on project type
        try:
            if project.type.name == 'development':
                # For development projects, use IssuePriority
                priorities = IssuePriority.query.filter(
                    IssuePriority.id.in_([1, 2, 3, 4, 5])  # Development priorities
                ).order_by(IssuePriority.order_index).all()
            else:
                # For general projects, use TaskPriority
                priorities = TaskPriority.query.order_by(TaskPriority.order_index).all()
                
            priority_data = [
                {
                    'id': p.id,
                    'name': p.name,
                    'color': p.color
                } for p in priorities
            ]
            # Ensure it's always an array
            if priority_data is None:
                priority_data = []
            print(f"Priority data: {priority_data}")
        except Exception as e:
            print(f"Error getting priorities: {str(e)}")
            priority_data = []
        
        # Get categories for the project (only relevant for general projects)
        category_data = []
        if project.type.name == 'general':
            categories = TaskCategory.query.filter_by(project_id=project_id).all()
            category_data = [
                {
                    'id': c.id,
                    'name': c.name,
                    'color': c.color
                } for c in categories
            ]
        
        # Get statuses based on project type
        if project.type.name == 'development':
            # For development projects, use IssueStatus
            statuses = IssueStatus.query.filter(
                IssueStatus.id.in_([1, 2, 3, 4])  # Development statuses: To Do, In Progress, Review, Done
            ).order_by(IssueStatus.order_index).all()
        else:
            # For general projects, use ProjectTaskStatus
            statuses = ProjectTaskStatus.query.filter_by(project_id=project_id).order_by(ProjectTaskStatus.order_index).all()
            if not statuses:
                # Use global task statuses if no project-specific statuses
                statuses = TaskStatus.query.order_by(TaskStatus.order_index).all()
        
        # Prepare board data
        board_data = []
        for status in statuses:
            column_tasks = []
            
            if project.type.name == 'development':
                # For development projects, get issues for this status
                issues = Issue.query.filter_by(
                    project_id=project_id,
                    status_id=status.id
                ).all()
                
                for issue in issues:
                    assignee_data = None
                    if issue.assignee:
                        assignee_data = {
                            'id': issue.assignee.id,
                            'name': issue.assignee.name,
                            'profile_picture_base64': issue.assignee.profile_picture_base64 
                        }
                    
                    priority_data = None
                    if issue.priority:
                        priority_data = {
                            'id': issue.priority.id,
                            'name': issue.priority.name,
                            'color': issue.priority.color
                        }
                    
                    issue_data = {
                        'id': issue.id,
                        'key': issue.issue_key,
                        'title': issue.summary,
                        'comments_count': len(issue.comments),  # Add comment count
                        'attachments_count': len(issue.attachments),  # Add attachment count
                        'description': issue.description,
                        'assignee': assignee_data,
                        'reporter_id': issue.reporter_id,
                        'priority': priority_data,
                        'due_date': issue.due_date.strftime('%Y-%m-%d') if issue.due_date else None,
                        'created_at': issue.created_at.strftime('%Y-%m-%d %H:%M:%S') if issue.created_at else None,
                        'type': {
                            'id': issue.type.id,
                            'name': issue.type.name
                        } if issue.type else None
                    }
                    column_tasks.append(issue_data)
            else:
                # For general projects, get tasks for this status
                tasks = Task.query.filter_by(
                    project_id=project_id,
                    status_id=status.id,
                    task_type='general'  # Ensure we're only getting general tasks
                ).all()
                
                for task in tasks:
                    assignee_data = None
                    if task.assignee:
                        assignee_data = {
                            'id': task.assignee.id,
                            'name': task.assignee.name,
                            'profile_picture_base64': task.assignee.profile_picture_base64 
                        }
                    
                    priority_data = None
                    if task.priority:
                        priority_data = {
                            'id': task.priority.id,
                            'name': task.priority.name,
                            'color': task.priority.color
                        }
                    
                    task_data = {
                        'id': task.id,
                        'key': task.task_key,
                        'title': task.title,
                        'comments_count': len(task.comments),  # Add comment count
                        'attachments_count': len(task.attachments), 
                        'description': task.description,
                        'assignee': assignee_data,
                        'created_by': task.created_by,
                        'priority': priority_data,
                        'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
                        'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S') if task.created_at else None
                    }
                    column_tasks.append(task_data)
            
            # Add column data with tasks/issues
            board_column = {
                'id': status.id,
                'name': status.name,
                'color': status.color,
                'issues': column_tasks  # We use "issues" to maintain API compatibility for both types
            }
            
            board_data.append(board_column)
        
        # Final check before returning data
        response_data = {
            'project': {
                'id': project.id,
                'name': project.name,
                'key': project.key,
                'team': team_members,
                'type': project.type.name,
                'lead_id': project.lead_id
            },
            'board': board_data,
            'priorities': priority_data,
            'categories': category_data
        }
        
        # Debug check on the data
        print("Final response structure:")
        print(f"- project: {type(response_data['project'])}")
        print(f"- project type: {response_data['project']['type']}")
        print(f"- board: {type(response_data['board'])}, is array: {isinstance(response_data['board'], list)}, length: {len(response_data['board'])}")
        print(f"- priorities: {type(response_data['priorities'])}, is array: {isinstance(response_data['priorities'], list)}, length: {len(response_data['priorities'])}")
        print(f"- categories: {type(response_data['categories'])}, is array: {isinstance(response_data['categories'], list)}, length: {len(response_data['categories'])}")
        
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Error in get_project_kanban_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': f'Failed to load Kanban board data: {str(e)}'
        }), 500

# Add this route to your routes.py file to handle task status updates

@tasks_bp.route("/api/tasks/<int:task_id>/update-status", methods=['POST'])
@login_required
def update_task_status(task_id):
    """Update the status of a task in a general project"""
    try:
        # Get the task and verify access
        task = Task.query.get_or_404(task_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and task.company_id != current_user.company_id:
            return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
        
        # Get new status ID from request
        data = request.get_json()
        if not data or 'status_id' not in data:
            return jsonify({'success': False, 'error': 'Status ID is required'}), 400
            
        new_status_id = data['status_id']
        
        # Validate status ID (ensure it belongs to this project)
        status = ProjectTaskStatus.query.filter_by(
            id=new_status_id,
            project_id=task.project_id
        ).first()
        
        if not status:
            return jsonify({'success': False, 'error': 'Invalid status ID for this project'}), 400
            
        # Store old status for history
        old_status_id = task.status_id
        
        # Update the task
        task.status_id = new_status_id
        task.updated_at = get_sri_lanka_time()
        
        # Check if the new status is a 'done' status, and update the is_done flag
        if status.is_done:
            task.is_done = 1
        else:
            task.is_done = 0  # Reset is_done if status is changed back to non-done
        
        # Create history entry
        history = TaskHistory(
            task_id=task.id,
            field_name='status_id',
            old_value=str(old_status_id) if old_status_id else None,
            new_value=str(new_status_id),
            changed_by=current_user.id,
            changed_at=get_sri_lanka_time()
        )
        
        # Add another history entry for the is_done flag if it changed
        if (status.is_done and task.is_done == 1) or (not status.is_done and task.is_done == 0):
            is_done_history = TaskHistory(
                task_id=task.id,
                field_name='is_done',
                old_value='0' if task.is_done == 0 else '1',
                new_value='1' if status.is_done else '0',
                changed_by=current_user.id,
                changed_at=get_sri_lanka_time()
            )
            db.session.add(is_done_history)
        
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Task status updated successfully',
            'task': {
                'id': task.id,
                'status_id': task.status_id,
                'status_name': task.status.name if task.status else None,
                'is_done': task.is_done
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating task status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tasks_bp.route("/api/issues/<int:issue_id>/update-status", methods=['POST'])
@login_required
def update_issue_status(issue_id):
    """Update the status of an issue in a development project"""
    try:
        # Get the issue and verify access
        issue = Issue.query.get_or_404(issue_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
            return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
        
        # Get new status ID from request
        data = request.get_json()
        if not data or 'status_id' not in data:
            return jsonify({'success': False, 'error': 'Status ID is required'}), 400
            
        new_status_id = data['status_id']
        
        # Validate status ID (depending on project type, validation may differ)
        # For development projects, check if the status is associated with the correct project
        status = IssueStatus.query.filter_by(
            id=new_status_id,
        ).first()
        
        if not status:
            return jsonify({'success': False, 'error': 'Invalid status ID'}), 400
            
        # Store old status for history
        old_status_id = issue.status_id
        old_status = issue.status.name if issue.status else None
        
        # Update the issue
        issue.status_id = new_status_id
        issue.updated_at = get_sri_lanka_time()
        
        # Create history entry
        history = IssueHistory(
            issue_id=issue.id,
            field_name='status_id',
            old_value=str(old_status_id) if old_status_id else None,
            new_value=str(new_status_id),
            changed_by=current_user.id,
            changed_at=get_sri_lanka_time()
        )
        
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Issue status updated successfully',
            'issue': {
                'id': issue.id,
                'status_id': issue.status_id,
                'status_name': issue.status.name if issue.status else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating issue status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/issue-types")
@login_required
def get_project_issue_types(project_id):
    """Get available issue types for a project"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # For development projects, get issue types
        if project.type.name == 'development':
            issue_types = IssueType.query.filter(
                IssueType.id.in_([1, 2, 3, 4, 5])  # Epic, Story, Task, Bug, Sub-task
            ).all()
        else:
            # For general projects we don't need to provide issue types
            issue_types = []
        
        return jsonify({
            'success': True,
            'issue_types': [{
                'id': type.id,
                'name': type.name,
                'description': type.description,
                'is_subtask': type.is_subtask
            } for type in issue_types]
        })
        
    except Exception as e:
        print(f"Error fetching issue types: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/epics")
@login_required
def get_project_epics(project_id):
    """Get epics for a project"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get epics for this project (issue_type_id=1 for Epic)
        epics = Issue.query.filter_by(
            project_id=project_id,
            issue_type_id=1
        ).all()
        
        return jsonify({
            'success': True,
            'epics': [{
                'id': epic.id,
                'key': epic.issue_key,
                'summary': epic.summary,
                'status': epic.status.name if epic.status else 'Unknown'
            } for epic in epics]
        })
        
    except Exception as e:
        print(f"Error fetching epics: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/issues", methods=['POST'])
@login_required
def create_project_issue(project_id):
    """API endpoint to create a new issue in a project"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # Check project type
        if project.type.name != 'development':
            return jsonify({
                'success': False,
                'error': 'Issues can only be created for development projects'
            }), 400
        
        # Check if request has form data or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Process form data for issue creation
            data = {
                'issue_type_id': request.form.get('issue_type_id'),
                'summary': request.form.get('summary'),
                'description': request.form.get('description'),
                'status_id': request.form.get('status_id'),
                'priority_id': request.form.get('priority_id'),
                'assignee_id': request.form.get('assignee_id'),
                'due_date': request.form.get('due_date'),
                'epic_id': request.form.get('epic_id') or None,
                'story_id': request.form.get('story_id') or None,
                'parent_id': request.form.get('parent_id') or None,
                'story_points': request.form.get('story_points'),
                'original_estimate': request.form.get('original_estimate')
            }
        else:
            # Process JSON data
            data = request.get_json()
            
        # Basic validation
        if not data.get('summary'):
            return jsonify({
                'success': False,
                'error': 'Summary is required'
            }), 400
            
        if not data.get('issue_type_id'):
            return jsonify({
                'success': False,
                'error': 'Issue type is required'
            }), 400
            
        if not data.get('status_id'):
            return jsonify({
                'success': False,
                'error': 'Status is required'
            }), 400
            
        # Generate a unique issue key
        issue_key = generate_issue_key(project)
        
        # Create the issue
        issue = Issue(
            project_id=project_id,
            issue_type_id=int(data['issue_type_id']),
            issue_key=issue_key,
            summary=data['summary'],
            description=data.get('description'),
            status_id=int(data['status_id']),
            priority_id=int(data['priority_id']) if data.get('priority_id') else None,
            assignee_id=int(data['assignee_id']) if data.get('assignee_id') else None,
            reporter_id=current_user.id,
            epic_id=int(data['epic_id']) if data.get('epic_id') else None,
            story_id=int(data['story_id']) if data.get('story_id') else None,
            parent_id=int(data['parent_id']) if data.get('parent_id') else None,
            story_points=float(data['story_points']) if data.get('story_points') else None,
            original_estimate=int(float(data['original_estimate']) * 60) if data.get('original_estimate') else None,  # Convert hours to minutes
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
            created_at=get_sri_lanka_time()
        )
        
        # Validate relationships
        errors = issue.validate_relationships()
        if errors:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400
        
        # Save to database
        db.session.add(issue)
        db.session.flush()  # Get the issue ID
        
        # Create initial history entry
        history = IssueHistory(
            issue_id=issue.id,
            field_name='status',
            new_value='Created',
            changed_by=current_user.id,
            changed_at=get_sri_lanka_time()
        )
        db.session.add(history)
        
        # Handle file attachments if present
        if request.files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename:
                    # Create attachment for the issue
                    attachment = IssueAttachment(
                        issue_id=issue.id,
                        file_name=secure_filename(file.filename),
                        file_data=file.read(),
                        file_type=file.content_type,
                        uploaded_by=current_user.id,
                        uploaded_at=get_sri_lanka_time()
                    )
                    db.session.add(attachment)
        
        # Commit all changes
        db.session.commit()
        
        # Return success response
        return jsonify({
            'success': True,
            'message': 'Issue created successfully',
            'issue': {
                'id': issue.id,
                'key': issue.issue_key,
                'summary': issue.summary
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating issue: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to create issue: {str(e)}'
        }), 500

def generate_issue_key(project):
    """Generate a unique issue key based on project key"""
    # Find the highest numeric part of existing issue keys
    last_issue = Issue.query.filter(Issue.issue_key.like(f"{project.key}-%")).order_by(
        Issue.issue_key.desc()
    ).first()
    
    if last_issue:
        try:
            # Extract the numeric part
            key_parts = last_issue.issue_key.split('-')
            if len(key_parts) > 1:
                last_number = int(key_parts[-1])
                new_number = last_number + 1
            else:
                new_number = 1
        except (ValueError, IndexError):
            # If there was an issue parsing the key, start from 1
            new_number = 1
    else:
        # No existing issues, start from 1
        new_number = 1
    
    # Format with padding to ensure consistent sorting
    return f"{project.key}-{new_number:04d}"


@tasks_bp.route("/api/projects/<int:project_id>/task-priorities")
@login_required
def get_task_priorities(project_id):
    """Get priorities for tasks in general projects"""
    try:
        # Check permission first
        project = Project.query.get_or_404(project_id)
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get task priorities
        priorities = TaskPriority.query.order_by(TaskPriority.order_index).all()
        for p in priorities:
            print(p.name)
        
        return jsonify({
            'success': True,
            'priorities': [{
                'id': priority.id,
                'name': priority.name,
                'color': priority.color,
                'order_index': priority.order_index
            } for priority in priorities]
        })
        
    except Exception as e:
        print(f"Error fetching task priorities: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route("/api/projects/<int:project_id>/issue-priorities")
@login_required
def get_issue_priorities(project_id):
    """Get priorities for issues in development projects"""
    try:
        # Check permission first
        project = Project.query.get_or_404(project_id)
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and project.company_id != current_user.company_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get issue priorities (ids 1-5 are for development projects)
        priorities = IssuePriority.query.filter(
            IssuePriority.id.in_([1, 2, 3, 4, 5])
        ).order_by(IssuePriority.order_index).all()
        for p in priorities:
            print(p.name)
        
        return jsonify({
            'success': True,
            'priorities': [{
                'id': priority.id,
                'name': priority.name,
                'color': priority.color,
                'order_index': priority.order_index
            } for priority in priorities]
        })
        
    except Exception as e:
        print(f"Error fetching issue priorities: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tasks_bp.route('/api/categories/<int:category_id>', methods=['GET'])
@login_required
def get_category_by_category_id(category_id):
    """Get category details by category ID"""
    try:
        # Find the category
        category = TaskCategory.query.get(category_id)
        
        if not category:
            return jsonify({
                'success': False,
                'error': 'Category not found'
            }), 404
        
        # Return category details
        return jsonify({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'color': category.color,
                'description': category.description
            }
        })
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error getting category: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@tasks_bp.route('/api/tasks/<int:task_id>/category', methods=['GET'])
@login_required
def get_task_category(task_id):
    """Get category details for a specific task"""
    try:
        # Find the task
        task = Task.query.get(task_id)
        
        if not task:
            return jsonify({
                'success': False,
                'error': 'Task not found'
            }), 404
        
        # Check if task has a category
        if not task.category_id:
            return jsonify({
                'success': False,
                'error': 'Task has no category assigned'
            }), 404
        
        # Find the category
        category = TaskCategory.query.get(task.category_id)
        
        if not category:
            return jsonify({
                'success': False,
                'error': 'Category not found'
            }), 404
        
        # Return category details
        return jsonify({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'color': category.color,
                'description': category.description
            }
        })
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error getting task category: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Add this route to the routes.py file to handle issue attachments

@tasks_bp.route("/api/issues/<int:issue_id>/attachments", methods=['POST'])
@login_required
def add_issue_attachment(issue_id):
    """API endpoint to add attachments to an existing issue"""
    try:
        # Get the issue and verify access
        issue = Issue.query.get_or_404(issue_id)
        
        # Check permission
        if not (current_user.assigned_role.role_name in ['admin', 'user']) and issue.project.company_id != current_user.company_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Check if files were included in the request
        files = request.files.getlist('file')
        if not files or all(not file.filename for file in files):
            return jsonify({
                'success': False,
                'error': 'No files uploaded'
            }), 400
        
        # Process each file
        attachments = []
        for file in files:
            if file and file.filename:
                # Create a secure filename to prevent path traversal attacks
                filename = secure_filename(file.filename)
                
                # Create attachment
                attachment = IssueAttachment(
                    issue_id=issue_id,
                    file_name=filename,
                    file_data=file.read(),
                    file_type=file.content_type,
                    uploaded_by=current_user.id,
                    uploaded_at=get_sri_lanka_time()
                )
                db.session.add(attachment)
                
                attachments.append({
                    'name': filename,
                    'type': file.content_type
                })
        
        # Create history entry for the attachment upload
        history = IssueHistory(
            issue_id=issue_id,
            field_name='attachments',
            old_value='',  # No need to track old attachments
            new_value=f"Added {len(attachments)} attachments",
            changed_by=current_user.id,
            changed_at=get_sri_lanka_time()
        )
        db.session.add(history)
        
        # Commit changes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {len(attachments)} attachments',
            'attachments': attachments
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding issue attachments: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500