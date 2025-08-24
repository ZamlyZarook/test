from datetime import datetime

def validate_project_dates(start_date_str, end_date_str):
    """
    Validates that project end date is not before start date.
    Returns (is_valid, error_message) tuple.
    """
    # If either date is missing, validation passes
    if not start_date_str or not end_date_str:
        return True, None
        
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        if end_date < start_date:
            return False, "End date cannot be before start date"
            
        return True, None
        
    except ValueError as e:
        return False, "Invalid date format. Please use YYYY-MM-DD"
    
def calculate_epic_progress(epic):
    """Calculate progress percentage for an epic based on completed stories/tasks"""
    total_stories = len(epic.stories)
    if total_stories == 0:
        return 0
        
    completed_stories = len([s for s in epic.stories if s.status == 'Completed'])
    return int((completed_stories / total_stories) * 100)