#!/bin/bash

# Create project directories
mkdir -p app/{static/{css,js,img},templates,models}

# Create required files
touch app/__init__.py
touch app/routes.py
touch app/models.py
touch app/forms.py
touch config.py
touch run.py
touch requirements.txt
touch .env

# Create static directories
mkdir -p app/static/uploads/qrcodes

# Create necessary files
touch app/models/__init__.py
touch app/controllers/__init__.py
touch config.py
touch run.py
touch create_db.py
touch .env

# Create template files
touch app/templates/base.html
touch app/templates/admin/dashboard.html
touch app/templates/admin/merchants.html
touch app/templates/admin/schemes.html
touch app/templates/admin/coupons.html
touch app/templates/merchant/dashboard.html
touch app/templates/merchant/redeem.html
touch app/templates/auth/login.html
touch app/templates/auth/register.html

# Create static asset directories
mkdir -p app/static/assets
mkdir -p app/static/css
mkdir -p app/static/js
mkdir -p app/static/img
mkdir -p app/static/vendor

# Create template directories
mkdir -p app/templates/includes
mkdir -p app/templates/admin
mkdir -p app/templates/auth
mkdir -p app/templates/merchant

# Create empty files for base templates
touch app/templates/includes/header.html
touch app/templates/includes/sidebar.html
touch app/templates/includes/footer.html

# Create example template files for each section
touch app/templates/admin/dashboard.html
touch app/templates/auth/login.html
touch app/templates/auth/register.html
touch app/templates/merchant/dashboard.html

# Create empty files for custom CSS and JS
touch app/static/css/style.css
touch app/static/js/main.js

# Make the script executable
chmod +x create_project.sh 