import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
import logging
from logging.handlers import RotatingFileHandler
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind
import time
import json as js


# Initialization
app = Flask(__name__)
app.secret_key = 'secret'
COURSE_FILE = 'course_catalog.json'

trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer("course-info-portal")

# Configure Jaeger Exporter
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",  
    agent_port=6831,             
)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

FlaskInstrumentor().instrument_app(app)

# Utility Functions
def load_courses():
    """Load courses from the JSON file."""
    if not os.path.exists(COURSE_FILE):
        return []  # Return an empty list if the file doesn't exist
    with open(COURSE_FILE, 'r') as file:
        return json.load(file)


def save_courses(data):
    """Save new course data to the JSON file."""
    courses = load_courses()  # Load existing courses
    courses.append(data)  # Append the new course
    with open(COURSE_FILE, 'w') as file:
        json.dump(courses, file, indent=4)


# Structured Logging in JSON format
log_file = "app.log"  
log_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 5, backupCount=2)  
log_handler.setLevel(logging.INFO)  

# Format log messages in JSON
log_formatter = logging.Formatter(
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
log_handler.setFormatter(log_formatter)

# Attach the handler to Flask's logger
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# Route Tracking (Counters)
route_counts = {
    'index': 0,
    'catalog': 0,
    'add_course': 0,
    'course_details': 0
}

# Error Tracking
error_counts = {
    'missing_fields': 0,
    'duplicate_code': 0
}

# Routes
@app.route('/')
def index():
    with tracer.start_as_current_span("index") as span:
        span.set_attribute("route", "/")
        span.set_attribute("request.method", request.method)
        span.set_attribute("user.ip", request.remote_addr)
        
        route_counts['index'] += 1  # Increment route counter
        start_time = time.time()  # Start timer for processing time
        
        app.logger.info("Course webpage accessed.")
        
        processing_time = time.time() - start_time  # Calculate processing time
        span.set_attribute("processing_time", processing_time)
        
        return render_template('index.html')

@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("course_catalog") as span:
        span.set_attribute("route", "/catalog")
        span.set_attribute("request.method", request.method)
        span.set_attribute("user.ip", request.remote_addr)
        
        route_counts['catalog'] += 1  # Increment route counter
        start_time = time.time()  # Start timer for processing time
        
        # Load courses
        with tracer.start_as_current_span("load_courses") as load_span:
            courses = load_courses()
            load_span.set_attribute("course_count", len(courses))
        
        # Render catalog page
        with tracer.start_as_current_span("render_catalog") as render_span:
            render_span.set_attribute("course_count", len(courses))
        
        processing_time = time.time() - start_time  # Calculate processing time
        span.set_attribute("processing_time", processing_time)
        
        app.logger.info(f"Course catalog page loaded with {len(courses)} courses.")
        
        return render_template('course_catalog.html', courses=courses)

@app.route('/course/<code>')
def course_details(code):
    with tracer.start_as_current_span("course_details") as span:
        span.set_attribute("route", "/course/<code>")
        span.set_attribute("request.method", request.method)
        span.set_attribute("user.ip", request.remote_addr)
        span.set_attribute("course.code", code)

        route_counts['course_details'] += 1  # Increment route counter
        start_time = time.time()  # Start timer for processing time

        # Load course data
        with tracer.start_as_current_span("load_course_data") as load_span:
            courses = load_courses()
            course = next((course for course in courses if course['code'] == code), None)
            load_span.set_attribute("course_found", bool(course))
        
        if not course:
            span.add_event("course_not_found", attributes={"course_code": code})
            flash(f"No course found with code '{code}'.", "error")
            error_counts['missing_fields'] += 1  # Increment error counter
            return redirect(url_for('course_catalog'))

        # Log and return course details
        span.set_attribute("course.name", course['name'])
        span.set_attribute("course.instructor", course['instructor'])
        span.add_event("course_found", attributes=course)
        
        app.logger.info(f"Course details page accessed for course {course['code']} - {course['name']}")
        
        processing_time = time.time() - start_time  # Calculate processing time
        span.set_attribute("processing_time", processing_time)

        return render_template('course_details.html', course=course)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    with tracer.start_as_current_span("add_course") as span:
        span.set_attribute("route", "/add_course")
        span.set_attribute("request.method", request.method)
        span.set_attribute("user.ip", request.remote_addr)
        
        route_counts['add_course'] += 1  # Incrementing route counter
        start_time = time.time()  # Staring the timer for processing time

        if request.method == 'POST':
            with tracer.start_as_current_span("handle_form_submission") as form_span:
                course_data = {
                    "name": request.form.get("name"),
                    "code": request.form.get("code"),
                    "instructor": request.form.get("instructor"),
                    "semester": request.form.get("semester"),
                    "schedule": request.form.get("schedule"),
                    "classroom": request.form.get("classroom"),
                    "prerequisites": request.form.get("prerequisites"),
                    "grading": request.form.get("grading"),
                    "description": request.form.get("description"),
                }
                
                form_span.set_attribute("course.name", course_data.get("name"))
                form_span.set_attribute("course.code", course_data.get("code"))
                form_span.set_attribute("course.instructor", course_data.get("instructor"))
                
                # Validation: Checking for the missing required fields
                missing_fields = [key for key, value in course_data.items() if not value and key in {"name", "code", "instructor", "semester"}]
                
                if missing_fields:
                    
                    missing_fields_str = ", ".join(missing_fields)

                    app.logger.error(f"Validation failed: Missing required fields {missing_fields_str} ")
                    error_counts['missing_fields'] += 1  # Increment error counter
                    span.add_event("validation_failed", attributes={"missing_fields": missing_fields})
                    flash(f"The following fields are required: {missing_fields_str}", "error")
                    return redirect(url_for("add_course"))
                
                # Checking for duplicate course code entered
                with tracer.start_as_current_span("check_duplicate_code") as dup_span:
                    courses = load_courses()
                    duplicate_course = next((course for course in courses if course["code"] == course_data["code"]), None)
                    dup_span.set_attribute("duplicate_found", bool(duplicate_course))

                    if duplicate_course:
                        app.logger.error(f"Duplicate course code detected: {course_data['code']}")
                        error_counts['duplicate_code'] += 1  # Incrementing the error counter
                        span.add_event("duplicate_course_code", attributes={"course_code": course_data["code"]})
                        flash(f"A course with the code '{course_data['code']}' already exists.", "error")
                        return redirect(url_for("add_course"))

                # Save the new course
                with tracer.start_as_current_span("save_course_data") as save_span:
                    save_courses(course_data)
                    save_span.set_attribute("course.saved", True)

                app.logger.info(f"Course added successfully: {course_data['code']} - {course_data['name']}")
                span.add_event("course_added", attributes=course_data)
                flash("Course added successfully!", "success")
                return redirect(url_for('course_catalog'))

        span.add_event("add_course_page_accessed")
        processing_time = time.time() - start_time  # processing time
        span.set_attribute("processing_time", processing_time)
        
        return render_template('add_course.html')

if __name__ == '__main__':
    app.run(debug=True)
