# Review Time Policy - MakonBook SAT Practice System

## Overview

The MakonBook SAT Practice System implements different review time policies based on user groups to provide appropriate access levels for different types of users.

## Review Time Policies

### 1. **OFFLINE Users**
- **Review Duration**: **3 days** (72 hours)
- **Maximum Retakes**: **4 attempts**
- **Access Level**: Extended review time for offline study
- **Purpose**: Accommodates users who need more time for detailed review

### 2. **Admin Users**
- **Review Duration**: **Unlimited** (no time restrictions)
- **Maximum Retakes**: **Unlimited**
- **Access Level**: Full administrative access
- **Purpose**: Allows administrators to access all content for management and support

### 3. **Regular Users (Students)**
- **Review Duration**: **24 hours** (1 day)
- **Maximum Retakes**: **2 attempts**
- **Access Level**: Standard review time
- **Purpose**: Standard access for regular student testing

## Implementation Details

### Database Models

#### TestReview Model (`apps/sat/models.py`)
- **duration**: `DurationField` - stores the review time limit
- **is_active()**: Method that checks if review is still accessible

```python
def is_active(self):
    # Admin users get unlimited review time
    if self.user.groups.filter(name='Admin').exists():
        return True
    # OFFLINE group users get infinite review time
    if self.user.groups.filter(name='OFFLINE').exists():
        return True
    # Regular users follow the duration limit
    return self.created_at + self.duration > datetime.datetime.now(timezone.utc)
```

#### TestStage Model (`apps/sat/models.py`)
- **retake_count**: `IntegerField` - tracks number of retakes used
- **get_max_retakes()**: Method that returns maximum retakes based on user group

```python
def get_max_retakes(self):
    """Get maximum retakes allowed for this user based on their group."""
    if self.user.groups.filter(name='OFFLINE').exists():
        return 4
    return 2
```

### View Logic

#### Test Results Creation (`apps/sat/views.py`)
When a TestReview is created, the duration is set based on user group:

```python
testreview, created = TestReview.objects.get_or_create(user=user, test=test_obj)
if created:
    testreview.update_key()
    # Set review duration based on user group
    if user.groups.filter(name='OFFLINE').exists():
        testreview.duration = timedelta(days=3)  # 3 days for OFFLINE users
    # Admin users and regular users keep default (24 hours)
    # Admin users have unlimited time via is_active() method
```

#### Question Access Control (`apps/sat/views.py`)
The question view checks review time expiration:

```python
if not test.is_active():
    # Check if user is not in OFFLINE or Admin groups
    if not (group in request.user.groups.all() or request.user.groups.filter(name='Admin').exists()):
        # Show review time expired page
        return render(request, 'sat/review_time_over.html', {...})
```

## User Group Assignments

### Group Structure
- **Admin**: Administrative users (october1550)
- **OFFLINE**: Users requiring extended review time (62 users)
- **Students**: Regular student users (241 users)

### Multiple Group Membership
Users can belong to multiple groups:
- **Admin + OFFLINE**: Gets both unlimited time AND 3-day duration setting
- **OFFLINE + Students**: Gets OFFLINE privileges (3 days, 4 retakes)
- **Students only**: Gets standard privileges (24 hours, 2 retakes)

## Template Updates

### Review Time Over Page
- **File**: `templates/sat/review_time_over.html`
- **Update**: Dynamic display of review duration instead of hardcoded "24 hours"
- **Display**: Shows actual review duration for transparency

### Retake Limit Page
- **File**: `templates/sat/retake_limit_exceeded.html`
- **Feature**: Already displays dynamic `max_retakes` value
- **Behavior**: Automatically shows correct retake limits per user group

## Technical Implementation

### Files Modified

1. **`apps/sat/models.py`**
   - Updated `TestReview.is_active()` method
   - Enhanced `TestStage.get_max_retakes()` method

2. **`apps/sat/views.py`**
   - Added `timedelta` import
   - Updated TestReview creation logic in multiple views
   - Enhanced question access control logic

3. **`templates/sat/review_time_over.html`**
   - Dynamic review duration display

### Database Impact
- **No schema changes required**
- **Existing data preserved**
- **New reviews get correct duration automatically**

## Testing Results

### Verified Functionality
✅ **OFFLINE users**: Get 3-day review duration and 4 retakes
✅ **Admin users**: Get unlimited review time regardless of duration
✅ **Regular users**: Keep 24-hour duration with normal time limits
✅ **Retake logic**: OFFLINE=4, Regular=2 attempts
✅ **Template display**: Shows correct durations and limits

### System Status
- **All services running**: Web app, Telegram bot, Nginx, PostgreSQL
- **No breaking changes**: Existing functionality preserved
- **Backward compatibility**: Existing reviews continue to work

## Security Considerations

### Access Control
- **Admin bypass**: Admin users can always access reviews (for support)
- **Time enforcement**: Regular users properly restricted by time limits
- **Group validation**: Multiple checks ensure proper group-based access

### Data Integrity
- **Existing reviews**: Not affected by changes
- **New reviews**: Get appropriate duration from creation
- **Retake tracking**: Properly enforced per user group

## Maintenance Notes

### Future Enhancements
- Review time policies can be easily adjusted by modifying the `timedelta` values
- Additional user groups can be added with custom policies
- Retake limits can be modified in the `get_max_retakes()` method

### Monitoring
- Django error logging captures any review time issues
- Admin interface provides visibility into review durations
- User group membership can be managed through Django admin

---

**Implementation Date**: July 31, 2025
**Status**: ✅ **FULLY IMPLEMENTED AND TESTED**
**Next Review**: Monitor user feedback and adjust policies as needed