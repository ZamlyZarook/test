from flask_wtf import FlaskForm
from wtforms import HiddenField, SubmitField
from wtforms.validators import DataRequired

class KnowledgeBaseToggleForm(FlaskForm):
    """Form for toggling the status of a knowledge base"""
    kb_id = HiddenField('Knowledge Base ID', validators=[DataRequired()])
    submit = SubmitField('Toggle Status')

