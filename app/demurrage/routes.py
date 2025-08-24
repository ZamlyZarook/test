from datetime import datetime, date, timedelta
import calendar
from app.models.demurrage import NonWorkingDay, CompanyDemurrageConfig, DemurrageRateCard, DemurrageReasons, DemurrageRateCardTier
from app.models.user import CountryMaster, CurrencyMaster
from app.models.company import CompanyInfo
from app.models.cha import OsContainerSize, OsContainerType
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.demurrage import bp
from app import db
from app.demurrage_scheduler import manual_demurrage_check, daily_demurrage_check


def get_company_id():
    return current_user.company_id

# Non-Working Days routes
####################
@bp.route("/non-working-days")
@login_required
def non_working_days():
    # Get filter parameters
    country_id = request.args.get('country_id', type=int)
    day_type = request.args.get('type')
    search = request.args.get('search', '')
    per_page = int(request.args.get('per_page', 10))
    
    # Build query
    query = NonWorkingDay.query.join(CountryMaster)
    
    if country_id:
        query = query.filter(NonWorkingDay.country_id == country_id)
    
    if day_type:
        query = query.filter(NonWorkingDay.type == day_type)
    
    if search:
        query = query.filter(
            db.or_(
                NonWorkingDay.description.contains(search),
                CountryMaster.countryName.contains(search)
            )
        )
    
    # Get paginated results
    non_working_days = query.order_by(NonWorkingDay.date.desc()).limit(per_page).all()
    
    # Get countries for filter dropdown
    countries = CountryMaster.query.all()
    
    return render_template(
        "demurrage/non_working_days.html",
        title="Non-Working Days",
        non_working_days=non_working_days,
        countries=countries
    )


@bp.route("/non-working-day/new", methods=["GET", "POST"])
@login_required
def new_non_working_day():
    if request.method == "POST":
        date_str = request.form.get('date')
        day_type = request.form.get('type')
        country_id = request.form.get('country_id')
        description = request.form.get('description')
        
        # Validation
        if not all([date_str, day_type, country_id]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("demurrage.new_non_working_day"))
        
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for("demurrage.new_non_working_day"))
        
        # Check if date already exists for this country
        existing = NonWorkingDay.query.filter_by(
            date=date_obj, 
            country_id=country_id
        ).first()
        
        if existing:
            flash("This date already exists for the selected country.", "danger")
            return redirect(url_for("demurrage.new_non_working_day"))
        
        non_working_day = NonWorkingDay(
            date=date_obj,
            type=day_type,
            country_id=country_id,
            description=description or f"{day_type.replace('_', ' ').title()}",
            company_id=get_company_id()
        )
        
        db.session.add(non_working_day)
        db.session.commit()
        flash("Non-working day has been created!", "success")
        return redirect(url_for("demurrage.non_working_days"))
    
    # GET request
    countries = CountryMaster.query.all()
    return render_template(
        "demurrage/non_working_day_form.html",
        title="New Non-Working Day",
        countries=countries
    )


@bp.route("/non-working-day/<int:nwd_id>/edit", methods=["GET", "POST"])
@login_required
def edit_non_working_day(nwd_id):
    non_working_day = NonWorkingDay.query.get_or_404(nwd_id)
    
    if request.method == "POST":
        date_str = request.form.get('date')
        day_type = request.form.get('type')
        country_id = request.form.get('country_id')
        description = request.form.get('description')
        is_active = request.form.get('is_active') == 'on'
        
        # Validation
        if not all([date_str, day_type, country_id]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("demurrage.edit_non_working_day", nwd_id=nwd_id))
        
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for("demurrage.edit_non_working_day", nwd_id=nwd_id))
        
        # Check if date already exists for this country (excluding current record)
        existing = NonWorkingDay.query.filter_by(
            date=date_obj, 
            country_id=country_id
        ).filter(NonWorkingDay.id != nwd_id).first()
        
        if existing:
            flash("This date already exists for the selected country.", "danger")
            return redirect(url_for("demurrage.edit_non_working_day", nwd_id=nwd_id))
        
        non_working_day.date = date_obj
        non_working_day.type = day_type
        non_working_day.country_id = country_id
        non_working_day.description = description or f"{day_type.replace('_', ' ').title()}"
        non_working_day.is_active = is_active
        
        db.session.commit()
        flash("Non-working day has been updated!", "success")
        return redirect(url_for("demurrage.non_working_days"))
    
    # GET request
    countries = CountryMaster.query.all()
    return render_template(
        "demurrage/non_working_day_form.html",
        title="Edit Non-Working Day",
        countries=countries,
        non_working_day=non_working_day
    )


@bp.route("/non-working-day/<int:nwd_id>/delete", methods=["POST"])
@login_required
def delete_non_working_day(nwd_id):
    non_working_day = NonWorkingDay.query.get_or_404(nwd_id)
    db.session.delete(non_working_day)
    db.session.commit()
    flash("Non-working day has been deleted!", "success")
    return redirect(url_for("demurrage.non_working_days"))


@bp.route("/api/generate-weekends", methods=["POST"])
@login_required
def generate_weekends():
    """Generate weekend entries for a specific country and year with custom weekend days"""
    
    data = request.get_json()
    country_id = data.get('country_id')
    year = data.get('year')
    weekend_days = data.get('weekend_days', [])  # List of weekday numbers (0=Monday, 6=Sunday)
    
    # Validation
    if not country_id or not year:
        return jsonify({"success": False, "message": "Country and year are required"}), 400
    
    if not weekend_days or not isinstance(weekend_days, list):
        return jsonify({"success": False, "message": "Weekend days must be specified"}), 400
    
    # Validate weekend days are valid (0-6)
    if not all(isinstance(day, int) and 0 <= day <= 6 for day in weekend_days):
        return jsonify({"success": False, "message": "Invalid weekend day values. Must be 0-6 (Monday-Sunday)"}), 400
    
    try:
        year = int(year)
        if year < 2020 or year > 2030:
            return jsonify({"success": False, "message": "Year must be between 2020 and 2030"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid year format"}), 400
    
    # Get country info
    country = CountryMaster.query.get(country_id)
    if not country:
        return jsonify({"success": False, "message": "Country not found"}), 404
    
    try:
        # Generate weekends for the year
        weekends = []
        existing_count = 0
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        
        # Day names for descriptions
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        current_date = start_date
        while current_date <= end_date:
            # Check if current date's weekday is in the selected weekend days
            if current_date.weekday() in weekend_days:
                day_name = day_names[current_date.weekday()]
                
                # Check if this date already exists
                existing = NonWorkingDay.query.filter_by(
                    date=current_date,
                    country_id=country_id
                ).first()
                
                if existing:
                    existing_count += 1
                else:
                    weekends.append({
                        'date': current_date,
                        'description': f"{day_name}"
                    })
            
            current_date += timedelta(days=1)
        
        # Insert weekends into database
        created_count = 0
        for weekend in weekends:
            try:
                # Create NonWorkingDay without created_by field
                non_working_day = NonWorkingDay(
                    date=weekend['date'],
                    type='WEEKEND',
                    country_id=country_id,
                    description=weekend['description'],
                    company_id=get_company_id(),
                    is_active=True
                )
                db.session.add(non_working_day)
                created_count += 1
            except Exception as e:
                print(f"Error creating weekend entry for {weekend['date']}: {str(e)}")
                continue
        
        # Commit all changes
        db.session.commit()
        
        # Prepare response message
        selected_day_names = [day_names[day] for day in sorted(weekend_days)]
        message_parts = []
        
        if created_count > 0:
            message_parts.append(f"Successfully created {created_count} weekend entries")
        
        if existing_count > 0:
            message_parts.append(f"skipped {existing_count} existing entries")
        
        message = f"{' and '.join(message_parts)} for {', '.join(selected_day_names)} in {country.countryName} ({year})"
        
        return jsonify({
            "success": True, 
            "message": message,
            "details": {
                "created": created_count,
                "existing": existing_count,
                "total_processed": created_count + existing_count,
                "country": country.countryName,
                "year": year,
                "weekend_days": selected_day_names
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error generating weekends: {str(e)}")
        return jsonify({
            "success": False, 
            "message": f"An error occurred while generating weekends: {str(e)}"
        }), 500

# Company Demurrage Configuration routes
####################
@bp.route("/company-demurrage-configs")
@login_required
def company_demurrage_configs():
    # Get filter parameters
    company_id = request.args.get('company_id', type=int)
    country_id = request.args.get('country_id', type=int)
    status = request.args.get('status')
    search = request.args.get('search', '')
    per_page = int(request.args.get('per_page', 10))
    
    # Build query
    query = CompanyDemurrageConfig.query.join(CompanyInfo).join(CountryMaster)
    
    # Apply company filter based on user permissions
    if current_user.is_super_admin != 1:
        query = query.filter(CompanyDemurrageConfig.company_id == get_company_id())
    elif company_id:
        query = query.filter(CompanyDemurrageConfig.company_id == company_id)
    
    if country_id:
        query = query.filter(CompanyDemurrageConfig.country_id == country_id)
    
    if status == 'active':
        query = query.filter(CompanyDemurrageConfig.is_active == True)
    elif status == 'inactive':
        query = query.filter(CompanyDemurrageConfig.is_active == False)
    
    if search:
        query = query.filter(
            db.or_(
                CompanyInfo.company_name.contains(search),
                CountryMaster.countryName.contains(search)
            )
        )
    
    # Get paginated results
    configs = query.order_by(CompanyDemurrageConfig.created_at.desc()).limit(per_page).all()
    
    # Get companies and countries for filters
    if current_user.is_super_admin == 1:
        companies = CompanyInfo.query.all()
    else:
        companies = CompanyInfo.query.filter_by(id=get_company_id()).all()
    
    countries = CountryMaster.query.all()
    
    return render_template(
        "demurrage/company_demurrage_configs.html",
        title="Company Demurrage Configurations",
        configs=configs,
        companies=companies,
        countries=countries
    )


@bp.route("/company-demurrage-config/new", methods=["GET", "POST"])
@login_required
def new_company_demurrage_config():
    if request.method == "POST":
        company_id = request.form.get('company_id')
        demurrage_days_threshold = request.form.get('demurrage_days_threshold')
        country_id = request.form.get('country_id')
        exclude_weekends = request.form.get('exclude_weekends') == 'on'
        exclude_holidays = request.form.get('exclude_holidays') == 'on'
        
        # Validation
        if not all([company_id, demurrage_days_threshold, country_id]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("demurrage.new_company_demurrage_config"))
        
        # Validate threshold is positive integer
        try:
            threshold = int(demurrage_days_threshold)
            if threshold <= 0:
                flash("Demurrage days threshold must be a positive number.", "danger")
                return redirect(url_for("demurrage.new_company_demurrage_config"))
        except ValueError:
            flash("Invalid demurrage days threshold format.", "danger")
            return redirect(url_for("demurrage.new_company_demurrage_config"))
        
        # Check if configuration already exists for this company and country
        existing = CompanyDemurrageConfig.query.filter_by(
            company_id=company_id,
            country_id=country_id
        ).first()
        
        if existing:
            flash("Configuration already exists for this company and country combination.", "danger")
            return redirect(url_for("demurrage.new_company_demurrage_config"))
        
        # Check permissions
        if current_user.is_super_admin != 1 and int(company_id) != get_company_id():
            flash("You don't have permission to create configuration for this company.", "danger")
            return redirect(url_for("demurrage.company_demurrage_configs"))
        
        config = CompanyDemurrageConfig(
            company_id=company_id,
            demurrage_days_threshold=threshold,
            country_id=country_id,
            exclude_weekends=exclude_weekends,
            exclude_holidays=exclude_holidays
        )
        
        db.session.add(config)
        db.session.commit()
        flash("Company demurrage configuration has been created!", "success")
        return redirect(url_for("demurrage.company_demurrage_configs"))
    
    # GET request
    if current_user.is_super_admin == 1:
        companies = CompanyInfo.query.all()
    else:
        companies = CompanyInfo.query.filter_by(id=get_company_id()).all()
    
    countries = CountryMaster.query.all()
    
    return render_template(
        "demurrage/company_demurrage_config_form.html",
        title="New Company Demurrage Configuration",
        companies=companies,
        countries=countries
    )


@bp.route("/company-demurrage-config/<int:config_id>/edit", methods=["GET", "POST"])
@login_required
def edit_company_demurrage_config(config_id):
    config = CompanyDemurrageConfig.query.get_or_404(config_id)
    
    # Check permissions
    if current_user.is_super_admin != 1 and config.company_id != get_company_id():
        flash("You don't have permission to edit this configuration.", "danger")
        return redirect(url_for("demurrage.company_demurrage_configs"))
    
    if request.method == "POST":
        company_id = request.form.get('company_id')
        demurrage_days_threshold = request.form.get('demurrage_days_threshold')
        country_id = request.form.get('country_id')
        exclude_weekends = request.form.get('exclude_weekends') == 'on'
        exclude_holidays = request.form.get('exclude_holidays') == 'on'
        is_active = request.form.get('is_active') == 'on'
        
        # Validation
        if not all([company_id, demurrage_days_threshold, country_id]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("demurrage.edit_company_demurrage_config", config_id=config_id))
        
        # Validate threshold is positive integer
        try:
            threshold = int(demurrage_days_threshold)
            if threshold <= 0:
                flash("Demurrage days threshold must be a positive number.", "danger")
                return redirect(url_for("demurrage.edit_company_demurrage_config", config_id=config_id))
        except ValueError:
            flash("Invalid demurrage days threshold format.", "danger")
            return redirect(url_for("demurrage.edit_company_demurrage_config", config_id=config_id))
        
        # Check if configuration already exists for this company and country (excluding current)
        existing = CompanyDemurrageConfig.query.filter_by(
            company_id=company_id,
            country_id=country_id
        ).filter(CompanyDemurrageConfig.id != config_id).first()
        
        if existing:
            flash("Configuration already exists for this company and country combination.", "danger")
            return redirect(url_for("demurrage.edit_company_demurrage_config", config_id=config_id))
        
        # Check permissions for company change
        if current_user.is_super_admin != 1 and int(company_id) != get_company_id():
            flash("You don't have permission to assign configuration to this company.", "danger")
            return redirect(url_for("demurrage.edit_company_demurrage_config", config_id=config_id))
        
        config.company_id = company_id
        config.demurrage_days_threshold = threshold
        config.country_id = country_id
        config.exclude_weekends = exclude_weekends
        config.exclude_holidays = exclude_holidays
        config.is_active = is_active
        
        db.session.commit()
        flash("Company demurrage configuration has been updated!", "success")
        return redirect(url_for("demurrage.company_demurrage_configs"))
    
    # GET request
    if current_user.is_super_admin == 1:
        companies = CompanyInfo.query.all()
    else:
        companies = CompanyInfo.query.filter_by(id=get_company_id()).all()
    
    countries = CountryMaster.query.all()
    
    return render_template(
        "demurrage/company_demurrage_config_form.html",
        title="Edit Company Demurrage Configuration",
        companies=companies,
        countries=countries,
        config=config
    )


@bp.route("/company-demurrage-config/<int:config_id>/delete", methods=["POST"])
@login_required
def delete_company_demurrage_config(config_id):
    config = CompanyDemurrageConfig.query.get_or_404(config_id)
    
    # Check permissions
    if current_user.is_super_admin != 1 and config.company_id != get_company_id():
        flash("You don't have permission to delete this configuration.", "danger")
        return redirect(url_for("demurrage.company_demurrage_configs"))
    
    db.session.delete(config)
    db.session.commit()
    flash("Company demurrage configuration has been deleted!", "success")
    return redirect(url_for("demurrage.company_demurrage_configs"))

@bp.route("/manual-demurrage-check", methods=["GET"])
@login_required     
def manual_demurrage_check():
    """
    Manual trigger for demurrage check - useful for testing
    """
    print("MANUAL DEMURRAGE CHECK TRIGGERED")
    return daily_demurrage_check()




@bp.route('/rate-cards')
@login_required
def rate_cards():
    """List all demurrage rate cards with filtering and pagination"""
    
    # Get filter parameters
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    country = request.args.get('country', '')
    per_page = int(request.args.get('per_page', 10))
    
    # Build query
    query = DemurrageRateCard.query
    
    # Apply filters
    if search:
        query = query.filter(
            DemurrageRateCard.rate_card_name.contains(search) |
            DemurrageRateCard.description.contains(search)
        )
    
    if status == 'active':
        query = query.filter(DemurrageRateCard.is_active == True)
    elif status == 'inactive':
        query = query.filter(DemurrageRateCard.is_active == False)
    
    if country:
        query = query.filter(DemurrageRateCard.country_id == country)
    
    # Order by created date (newest first)
    query = query.order_by(DemurrageRateCard.created_at.desc())
    
    # Get all rate cards with tiers
    rate_cards = query.all()
    
    # Get countries for filter dropdown
    countries = CountryMaster.query.order_by(CountryMaster.countryName).all()
    
    return render_template('demurrage/rate_cards_list.html', 
                         rate_cards=rate_cards, 
                         countries=countries)


@bp.route('/rate-cards/new', methods=['GET', 'POST'])
@login_required
def new_rate_card():
    """Create new demurrage rate card"""
    
    if request.method == 'POST':
        try:
            # Create new rate card
            rate_card = DemurrageRateCard(
                rate_card_name=request.form.get('rate_card_name'),
                country_id=request.form.get('country_id'),
                company_id=request.form.get('company_id') if request.form.get('company_id') else None,
                description=request.form.get('description'),
                container_size_id=request.form.get('container_size_id'),
                container_type_id=request.form.get('container_type_id'),
                demurrage_reason_id=request.form.get('demurrage_reason_id'),
                currency_id=request.form.get('currency_id'),
                port_code=request.form.get('port_code'),
                set_by_authority=request.form.get('set_by_authority'),
                approved_by=request.form.get('approved_by'),
                approval_reference=request.form.get('approval_reference'),
                is_active=bool(request.form.get('is_active')),
                created_by=current_user.id,
                created_at=datetime.now()
            )
            
            db.session.add(rate_card)
            db.session.flush()  # To get the rate_card.id
            
            # Process tiers
            tier_numbers = request.form.getlist('tier_number[]')
            from_days = request.form.getlist('from_day[]')
            to_days = request.form.getlist('to_day[]')
            rate_amounts = request.form.getlist('rate_amount[]')
            
            for i, tier_number in enumerate(tier_numbers):
                if tier_number and from_days[i] and rate_amounts[i]:
                    tier = DemurrageRateCardTier(
                        rate_card_id=rate_card.id,
                        tier_number=int(tier_number),
                        from_day=int(from_days[i]),
                        to_day=int(to_days[i]) if to_days[i] else None,
                        rate_amount=float(rate_amounts[i])
                    )
                    db.session.add(tier)
            
            db.session.commit()
            
            flash('Demurrage rate card created successfully!', 'success')
            return redirect(url_for('demurrage.rate_cards'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating rate card: {str(e)}', 'danger')
    
    # Get dropdown data
    countries = CountryMaster.query.order_by(CountryMaster.countryName).all()
    companies = CompanyInfo.query.filter(CompanyInfo.is_active == True).order_by(CompanyInfo.company_name).all()
    container_sizes = OsContainerSize.query.order_by(OsContainerSize.name).all()
    container_types = OsContainerType.query.order_by(OsContainerType.name).all()
    currencies = CurrencyMaster.query.order_by(CurrencyMaster.CurrencyCode).all()
    demurrage_reasons = DemurrageReasons.query.filter(DemurrageReasons.is_active == True).order_by(DemurrageReasons.reason_name).all()
    
    return render_template('demurrage/rate_card_form.html',
                         rate_card=None,
                         countries=countries,
                         companies=companies,
                         container_sizes=container_sizes,
                         container_types=container_types,
                         currencies=currencies,
                         demurrage_reasons=demurrage_reasons)


@bp.route('/rate-cards/<int:rate_card_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_rate_card(rate_card_id):
    """Edit existing demurrage rate card"""
    
    rate_card = DemurrageRateCard.query.get_or_404(rate_card_id)
    
    if request.method == 'POST':
        try:
            # Update rate card
            rate_card.rate_card_name = request.form.get('rate_card_name')
            rate_card.country_id = request.form.get('country_id')
            rate_card.company_id = request.form.get('company_id') if request.form.get('company_id') else None
            rate_card.description = request.form.get('description')
            rate_card.container_size_id = request.form.get('container_size_id')
            rate_card.container_type_id = request.form.get('container_type_id')
            rate_card.demurrage_reason_id = request.form.get('demurrage_reason_id')
            rate_card.currency_id = request.form.get('currency_id')
            rate_card.port_code = request.form.get('port_code')
            rate_card.set_by_authority = request.form.get('set_by_authority')
            rate_card.approved_by = request.form.get('approved_by')
            rate_card.approval_reference = request.form.get('approval_reference')
            rate_card.is_active = bool(request.form.get('is_active'))
            rate_card.updated_by = current_user.id
            rate_card.updated_at = datetime.now()
            
            # Delete existing tiers
            DemurrageRateCardTier.query.filter_by(rate_card_id=rate_card.id).delete()
            
            # Process new tiers
            tier_numbers = request.form.getlist('tier_number[]')
            from_days = request.form.getlist('from_day[]')
            to_days = request.form.getlist('to_day[]')
            rate_amounts = request.form.getlist('rate_amount[]')
            
            for i, tier_number in enumerate(tier_numbers):
                if tier_number and from_days[i] and rate_amounts[i]:
                    tier = DemurrageRateCardTier(
                        rate_card_id=rate_card.id,
                        tier_number=int(tier_number),
                        from_day=int(from_days[i]),
                        to_day=int(to_days[i]) if to_days[i] else None,
                        rate_amount=float(rate_amounts[i])
                    )
                    db.session.add(tier)
            
            db.session.commit()
            
            flash('Demurrage rate card updated successfully!', 'success')
            return redirect(url_for('demurrage.rate_cards'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating rate card: {str(e)}', 'danger')
    
    # Get dropdown data
    countries = CountryMaster.query.order_by(CountryMaster.countryName).all()
    companies = CompanyInfo.query.filter(CompanyInfo.is_active == True).order_by(CompanyInfo.company_name).all()
    container_sizes = OsContainerSize.query.order_by(OsContainerSize.name).all()
    container_types = OsContainerType.query.order_by(OsContainerType.name).all()
    currencies = CurrencyMaster.query.order_by(CurrencyMaster.CurrencyCode).all()
    demurrage_reasons = DemurrageReasons.query.filter(DemurrageReasons.is_active == True).order_by(DemurrageReasons.reason_name).all()
    
    return render_template('demurrage/rate_card_form.html',
                         rate_card=rate_card,
                         countries=countries,
                         companies=companies,
                         container_sizes=container_sizes,
                         container_types=container_types,
                         currencies=currencies,
                         demurrage_reasons=demurrage_reasons)


@bp.route('/rate-cards/<int:rate_card_id>/view')
@login_required
def view_rate_card(rate_card_id):
    """View demurrage rate card details"""
    
    rate_card = DemurrageRateCard.query.get_or_404(rate_card_id)
    
    return render_template('demurrage/rate_card_view.html', rate_card=rate_card)


@bp.route('/rate-cards/<int:rate_card_id>/delete', methods=['POST'])
@login_required
def delete_rate_card(rate_card_id):
    """Delete demurrage rate card"""
    
    try:
        rate_card = DemurrageRateCard.query.get_or_404(rate_card_id)
        
        # Store name for flash message
        rate_card_name = rate_card.rate_card_name
        
        # Delete will cascade to tiers automatically
        db.session.delete(rate_card)
        db.session.commit()
        
        flash(f'Demurrage rate card "{rate_card_name}" deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting rate card: {str(e)}', 'danger')
    
    return redirect(url_for('demurrage.rate_cards'))

@bp.route('/api/rate-cards/<int:rate_card_id>')
@login_required
def api_get_rate_card(rate_card_id):
    """API endpoint to get rate card details (for AJAX if needed)"""
    
    rate_card = DemurrageRateCard.query.get_or_404(rate_card_id)
    
    # Build tiers data
    tiers_data = []
    for tier in rate_card.tiers:
        tiers_data.append({
            'tier_number': tier.tier_number,
            'from_day': tier.from_day,
            'to_day': tier.to_day,
            'rate_amount': tier.rate_amount,
            'day_range_display': tier.day_range_display
        })
    
    return jsonify({
        'id': rate_card.id,
        'rate_card_name': rate_card.rate_card_name,
        'country': rate_card.country.countryName if rate_card.country else None,
        'company': rate_card.company.name if rate_card.company else None,
        'container_size': rate_card.container_size.name if rate_card.container_size else None,
        'container_type': rate_card.container_type.name if rate_card.container_type else None,
        'currency': rate_card.currency.CurrencyCode if rate_card.currency else None,
        'demurrage_reason': rate_card.demurrage_reason.reason_name if rate_card.demurrage_reason else None,
        'port_code': rate_card.port_code,
        'set_by_authority': rate_card.set_by_authority,
        'is_active': rate_card.is_active,
        'tiers': tiers_data,
        'created_at': rate_card.created_at.isoformat() if rate_card.created_at else None,
        'updated_at': rate_card.updated_at.isoformat() if rate_card.updated_at else None
    })






