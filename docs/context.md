# MakonBook SAT Practice System - Project Context

## Project Overview

**MakonBook** is a comprehensive Django-based SAT (Scholastic Assessment Test) practice system designed for students preparing for standardized tests. The system provides practice tests, scoring, certificates, and detailed analytics.

### Key Information
- **Project Name**: MakonBook SAT Practice System  
- **Framework**: Django 5.1.5
- **Database**: PostgreSQL 16.9 (migrated from SQLite3)
- **Domain**: https://makonbook.satmakon.com
- **Deployment**: uWSGI with 30 processes, 4 threads per process

## Architecture Overview

### Core Applications
The project is structured with two main Django apps:

1. **apps.base** - User management, authentication, and core functionality
2. **apps.sat** - SAT test management, questions, scoring, and practice system

### Database Architecture

#### Production Database (PostgreSQL)
- **Engine**: PostgreSQL 16.9 (django.db.backends.postgresql)
- **Database**: makonbook_sat
- **User**: makonbook_user
- **Features**: ACID compliance, advanced indexing, concurrent access
- **Migration**: Clean condensed migration system (2 files only)

#### Database Schema

##### User Management (apps.base)
- **EmailVerification**: Email verification tokens for user registration
- **UserProfile**: Extended user profiles with customizable test timing
  - English/Math time limits (default: 32/35 minutes)
  - Offline user support with unlimited time

##### SAT Testing System (apps.sat)
- **Test**: Main test containers with group-based access control
- **English_Question**: English section questions with passages, choices, explanations
- **Math_Question**: Math section questions with image support for choices and explanations
- **MakeupTest**: Alternative test system with custom question ordering
- **TestModule**: User answer tracking for each test section/module
- **TestReview**: Comprehensive scoring and certificate generation
- **BaseVideo**: Video management for lessons and explanations (HLS streaming)

### Question Structure
- **Modules**: Each test has Module 1 and Module 2 for both English and Math
- **Domains**: Questions categorized by skill domains (8 total)
- **Types**: Different question types with specific scoring rules (29 total)
- **Image Support**: Full support for question images, choice images, and explanation images

## Features

### Testing System
- **Practice Tests**: Full SAT practice with English and Math sections
- **Timed Testing**: Configurable time limits per section
- **Makeup Tests**: Alternative testing system for make-up exams
- **Scoring**: Automatic scoring with detailed analytics
- **Certificates**: Generated certificates stored in Cloudflare R2

### User Management
- **Registration/Login**: Complete authentication system with email verification
- **User Groups**: Role-based access (Admin, Tester, OFFLINE users)
- **Profile Management**: Customizable test time preferences
- **Clean System**: Fresh start capability with preserved admin user

### Content Management
- **Question Management**: Comprehensive question bank with images
- **Video Integration**: HLS video streaming for lessons and explanations
- **File Storage**: Cloudflare R2 integration for media files and certificates

### Analytics & Results
- **Detailed Scoring**: Domain-wise performance analysis
- **Rankings**: User performance comparisons
- **Test History**: Complete test attempt tracking
- **Results Export**: Certificate generation and user-specific results

## Technical Stack

### Backend
- **Django 5.1.5**: Web framework
- **Python 3.12.3**: Core programming language
- **PostgreSQL 16.9**: Production database with advanced features
- **uWSGI**: WSGI server for production

### Storage & Media
- **Cloudflare R2**: Primary file storage for images, videos, and certificates
- **django-storages**: S3-compatible storage backend with SigV4 signatures
- **Private/Public Storage**: Segregated storage for different content types

### Frontend
- **Django Templates**: Server-side rendering
- **JavaScript**: Interactive testing interface
- **Bootstrap/CSS**: Responsive design

### Dependencies
Key packages from requirements (r.txt):
- Django==5.1.5
- django-storages==1.14.4
- boto3==1.36.9 (for R2 storage)
- pillow==11.1.0 (image processing)
- PyMuPDF==1.25.2 (PDF handling for certificates)
- python-dotenv==1.0.1 (environment variables)
- psycopg2-binary==2.9.9 (PostgreSQL adapter)
- uWSGI==2.0.28 (production server)

## Configuration

### Environment Variables (.env)
The system uses `.env` file for production configuration:

#### Database Configuration
- **DB_ENGINE**: django.db.backends.postgresql
- **DB_NAME**: makonbook_sat
- **DB_USER**: makonbook_user
- **DB_PASSWORD**: Secure database password
- **DB_HOST**: localhost
- **DB_PORT**: 5432

#### Storage Configuration
- **R2_ACCESS_KEY_ID**: Cloudflare R2 access key
- **R2_SECRET_ACCESS_KEY**: Cloudflare R2 secret key
- **R2_BUCKET_NAME**: Storage bucket name (makonbook)
- **R2_ENDPOINT_URL**: R2 endpoint URL

#### Application Settings
- **EMAIL**: SMTP email for system notifications
- **EMAIL_PASSWORD**: SMTP password
- **DEBUG**: Production debug setting (False)
- **ALLOWED_HOSTS**: Comma-separated list of allowed hosts

### Security Features
- **SECRET_KEY**: Stored in separate config.ini file
- **HTTPS Settings**: Secure cookies and CSRF protection
- **CORS**: Configured for makonbook.satmakon.com
- **File Upload Security**: Separate public/private storage with signed URLs
- **Database Security**: PostgreSQL user with limited privileges

## Database Migration System

### Condensed Migration Architecture
- **Migration Files**: Only 2 clean files (base + sat apps)
- **No Conflicts**: Eliminated 50+ legacy migration files
- **Production Ready**: Clean schema matching current models exactly

### Migration Features
1. **Clean Architecture**: No legacy migration baggage
2. **Simple Maintenance**: Easy to understand and modify
3. **Fast Performance**: Optimized PostgreSQL schema
4. **Data Integrity**: 100% data preservation during migration
5. **Scalable**: Ready for production workloads

### Current Data Status
```
👥 Users: 1 (october1550 - admin user preserved)
📝 Tests: 57 (complete SAT practice tests)
📚 English Questions: 3,024
🔢 Math Questions: 2,364
🏷️ Question Domains: 8
📝 Question Types: 29
📊 Total Records: 5,447
```

## URL Structure

### Base URLs (/)
- `/` - Home page
- `/login/` - User login
- `/logout/` - User logout  
- `/register/` - User registration
- `/activate/<token>/` - Email verification
- `/edit-profile/` - Profile management
- `/software/` - Software information

### SAT URLs (/sat/)
- `/sat/practises/` - Test dashboard
- `/sat/practise/<test_id>` - Start practice test
- `/sat/question/<key>/<section>/<module>/<id>` - Individual questions
- `/sat/results/<test>` - Test results and scoring
- `/sat/results/certificate/<test>/` - Certificate generation (R2 storage)
- `/sat/rankings/<test>` - Performance rankings
- `/sat/enter-code/` - Secret code entry for special tests
- `/sat/dev/` - Development mode tools

### Admin URLs
- `/admin/` - Django admin interface

## Development Features

### Dev Mode
- Development tools accessible at `/sat/dev/`
- Special development views and utilities
- Testing and debugging features

### Data Management
- Clean slate system for fresh user starts
- Automated backup capabilities
- Condensed migration system for easy maintenance

## Deployment

### Production Setup
- **uWSGI Configuration**: 30 processes, 4 threads, socket-based
- **Database**: PostgreSQL 16.9 with connection pooling
- **Static Files**: Collected in staticfiles/ directory
- **Media Files**: Stored on Cloudflare R2 with global CDN
- **Certificates**: Generated and stored in R2 with signed URLs
- **Logging**: Centralized logging to /home/admin/makonbook/logs/
- **Performance**: Optimized for high-concurrency testing

### File Structure
```
makonbook/
├── apps/
│   ├── base/                      # User management
│   │   └── migrations/
│   │       └── 0001_initial.py    # Condensed base migration
│   └── sat/                       # SAT testing system
│       ├── storages.py            # R2 storage classes
│       ├── libs/certificate/      # Certificate generation
│       └── migrations/
│           └── 0001_initial.py    # Condensed SAT migration
├── satmakon/                      # Django project settings
├── templates/                     # HTML templates
├── static/                        # Static assets
├── staticfiles/                   # Collected static files
├── docs/                          # Project documentation
│   ├── context.md                 # This file
│   └── postgresql_migration_guide.md
├── db.sqlite3                     # Legacy SQLite database (backup)
├── .env                           # Environment configuration
├── env.example                    # Environment template
├── manage.py                      # Django management
├── r.txt                          # Requirements file
├── makonbook.ini                  # uWSGI configuration
└── README_MIGRATION.md            # Migration instructions
```

## Key Business Logic

### Test Flow
1. User selects practice test from dashboard
2. Test consists of English and Math sections, each with 2 modules
3. Questions are served dynamically with timing controls
4. Answers are submitted and stored in TestModule
5. Comprehensive scoring and certificate generation
6. Results stored in TestReview with performance analytics

### Scoring System
- Domain-based analysis for detailed feedback
- Automatic score calculation (400-1600 scale)
- Certificate generation with performance metrics stored in R2
- Ranking system for user comparison

### User Roles
- **Students**: Take practice tests, view results
- **OFFLINE Users**: Unlimited time for accessibility
- **Testers**: Access to additional test features  
- **Admins**: Full system access and management (october1550)

## Performance Optimizations

### Database Performance
- **PostgreSQL Indexing**: Optimized queries for large datasets
- **Connection Pooling**: Efficient database connection management
- **Condensed Migrations**: Fast schema operations
- **Clean Architecture**: No legacy overhead

### Application Performance
- **Static File Optimization**: CDN-ready static file serving
- **Media Optimization**: Cloudflare R2 for global content delivery
- **Certificate Storage**: R2 with signed URLs for security
- **Caching Strategy**: Strategic caching for frequently accessed data

### Scalability Features
- **Horizontal Scaling**: uWSGI multi-process architecture
- **Database Scaling**: PostgreSQL read replicas support
- **Storage Scaling**: Cloudflare R2 unlimited storage
- **Clean System**: Easy user data management

## Monitoring and Maintenance

### Health Checks
- **Database Connectivity**: Automated PostgreSQL connection testing
- **Storage Accessibility**: R2 storage health monitoring
- **Application Status**: Django deployment checks

### Backup Strategy
- **Automated Database Backups**: Regular PostgreSQL dumps
- **Data Integrity Verification**: Automated backup testing
- **Migration Backups**: JSON dumps before major changes
- **Disaster Recovery**: Complete restoration procedures

### Security Monitoring
- **Access Control**: Role-based permissions monitoring
- **File Upload Security**: Automated security scanning with R2
- **Database Security**: Regular PostgreSQL security audits
- **Certificate Security**: Signed URLs with expiration

## Recent Improvements

### Migration System Overhaul (July 2025)
- **Problem**: 50+ conflicting migration files causing deployment issues
- **Solution**: Condensed migration system with only 2 clean files
- **Result**: 100% successful PostgreSQL migration with zero data loss

### Certificate Storage Migration
- **Enhancement**: Moved certificate storage from local filesystem to Cloudflare R2
- **Benefits**: Global CDN, signed URLs, better security
- **Compatibility**: Maintains backward compatibility with legacy certificates

### System Cleanup
- **User Management**: Streamlined to preserve only essential admin user (october1550)
- **Data**: Clean slate for test reviews and modules while preserving content
- **Performance**: Optimized for fresh user onboarding

This system represents a sophisticated, production-ready SAT practice platform with comprehensive features for test management, user analytics, scalable content delivery, enterprise-grade PostgreSQL database architecture, and modern cloud storage integration.
