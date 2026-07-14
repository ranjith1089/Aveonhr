"""
Proposal module catalog - single source of truth for everything the
proposal builder can offer.

Three top-level tables:

    MODULES   - individual modules (CMS sub-modules, COE sub-modules,
                standalone offerings, add-ons)
    BUNDLES   - pre-built packages (Complete CMS, Complete COE, etc.)
    CATEGORIES- grouping shown in the form UI

The form lets the user either pick a BUNDLE or pick individual MODULES.
The view resolves the selection into a flat list of modules, computes
pricing and renders the proposal template.

Adding a new module or bundle later = a single dict entry here.
No HTML edits, no form edits.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict


class Module(TypedDict, total=False):
    code: str
    name: str
    category: str           # CATEGORIES key
    icon: str               # emoji for the card
    color: str              # hex accent
    short_desc: str         # 1-line pitch shown on the module card
    sub_features: list[str] # bullet list inside the card
    default_price_per_student: Decimal
    one_time_fee: Decimal   # zero unless module needs its own setup fee
    tag: str                # optional badge: "FREE", "ADD-ON", "POPULAR"


class Bundle(TypedDict, total=False):
    code: str
    name: str
    tagline: str
    modules: list[str]                  # list of module codes
    bundle_price_per_student: Decimal   # discounted bundle price
    standalone_total: Decimal           # sum if bought individually
    one_time_implementation_fee: Decimal
    waive_one_time_default: bool        # show as waived by default
    hero_color: str                     # main accent for hero gradient
    hero_gradient_end: str              # second color for gradient


# ---------------------------------------------------------------------------
# Categories - UI grouping for the form's "Custom" mode
# ---------------------------------------------------------------------------
CATEGORIES: dict[str, str] = {
    "CMS_CORE":      "CMS - Core Academic & Administration",
    "CMS_FINANCE":   "CMS - Finance & HR",
    "CMS_STUDENT":   "CMS - Student Services & Communication",
    "COE_CORE":      "COE - Examination Lifecycle",
    "COE_RESULTS":   "COE - Results, Revaluation & Certificates",
    "ADDON":         "Free Add-ons",
    "STANDALONE":    "Standalone Offerings",
}


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------
MODULES: dict[str, Module] = {

    # ==================== CMS - 25 modules (docx-aligned) ==================
    "CMS_ADMISSION": {
        "code": "CMS_ADMISSION",
        "name": "Admission & Enrollment Management",
        "category": "CMS_CORE",
        "icon": "🎓",
        "color": "#2E7D32",
        "short_desc": "Online admissions from enquiry to enrollment - portal, merit lists, certificates.",
        "sub_features": [
            "Online Admission Portal", "Lead & Enquiry Management",
            "Application Tracking", "Online Document Upload",
            "Merit List Generation", "Admission Workflow",
            "Candidate Evaluation", "Scholarship Management",
            "Online Fee Payment", "Student Registration",
            "Student ID Generation", "Certificate Verification",
            "Bulk Student Import", "Student Promotion",
            "Transfer Certificate (TC)", "Bonafide Certificate",
            "Migration Certificate",
        ],
        "default_price_per_student": Decimal("40"),
    },
    "CMS_SIS": {
        "code": "CMS_SIS",
        "name": "Student Information System (SIS)",
        "category": "CMS_CORE",
        "icon": "🧑‍🎓",
        "color": "#1565C0",
        "short_desc": "One complete digital profile per student - academic, personal and lifecycle.",
        "sub_features": [
            "Complete Student Profile", "Academic History",
            "Parent Information", "Medical Information",
            "Attendance History", "Discipline Records",
            "Hostel Details", "Transport Details",
            "Fee History", "Digital Student Profile",
            "Student Life Cycle Management",
        ],
        "default_price_per_student": Decimal("30"),
    },
    "CMS_ACADEMIC": {
        "code": "CMS_ACADEMIC",
        "name": "Academic Management",
        "category": "CMS_CORE",
        "icon": "📚",
        "color": "#E65100",
        "short_desc": "Programs, courses, CBCS, electives, lesson plans and faculty workload.",
        "sub_features": [
            "Academic Calendar", "Program Management",
            "Department Management", "Semester Management",
            "Batch Management", "Course Management",
            "Subject Management", "Curriculum Management",
            "CBCS", "Choice Based Electives",
            "Open Electives", "Fast Track Courses",
            "Value Added Courses", "Skill Development Courses",
            "Lesson Plan", "Teaching Plan",
            "Syllabus Coverage", "Faculty Workload",
            "Faculty Allocation",
        ],
        "default_price_per_student": Decimal("60"),
    },
    "CMS_OBE": {
        "code": "CMS_OBE",
        "name": "Outcome Based Education (OBE)",
        "category": "CMS_CORE",
        "icon": "🎯",
        "color": "#6A1B9A",
        "short_desc": "PEO/PO/CO frameworks with attainment analytics and NBA compliance.",
        "sub_features": [
            "Program Educational Objectives (PEO)", "Program Outcomes (PO)",
            "Program Specific Outcomes (PSO)", "Course Outcomes (CO)",
            "Learning Outcomes (LO)", "CO-PO Mapping",
            "CO Attainment", "PO Attainment",
            "Bloom's Taxonomy", "Graduate Attributes",
            "NBA Compliance Reports",
        ],
        "default_price_per_student": Decimal("35"),
    },
    "CMS_ATTENDANCE": {
        "code": "CMS_ATTENDANCE",
        "name": "Attendance Management",
        "category": "CMS_CORE",
        "icon": "🕒",
        "color": "#00838F",
        "short_desc": "Hour-wise and daily attendance with parent notifications and analytics.",
        "sub_features": [
            "Hour-wise Attendance", "Daily Attendance",
            "Online Attendance", "Attendance Correction Workflow",
            "Parent Notifications", "Attendance Analytics",
        ],
        "default_price_per_student": Decimal("20"),
    },
    "CMS_TIMETABLE": {
        "code": "CMS_TIMETABLE",
        "name": "Timetable Management",
        "category": "CMS_CORE",
        "icon": "📅",
        "color": "#C62828",
        "short_desc": "Conflict-free scheduling for classes, labs, faculty and rooms.",
        "sub_features": [
            "Master Timetable", "Faculty Timetable",
            "Student Timetable", "Classroom Allocation",
            "Laboratory Scheduling", "Smart Conflict Detection",
            "Timetable Publishing", "Mobile Timetable",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "CMS_LMS": {
        "code": "CMS_LMS",
        "name": "Learning Management System (LMS)",
        "category": "CMS_CORE",
        "icon": "💻",
        "color": "#283593",
        "short_desc": "Content, assignments, quizzes and online classes with learning analytics.",
        "sub_features": [
            "Course Content", "Video Lectures",
            "Study Materials", "Online Assignments",
            "Quiz", "MCQ Assessment",
            "Discussion Forum", "Online Classes",
            "Assignment Evaluation", "Digital Notes",
            "Learning Analytics",
        ],
        "default_price_per_student": Decimal("45"),
    },
    "CMS_EXAMINATION": {
        "code": "CMS_EXAMINATION",
        "name": "Examination & Controller of Examination (COE)",
        "category": "CMS_CORE",
        "icon": "📝",
        "color": "#1565C0",
        "short_desc": "The complete exam lifecycle - planning to result analytics.",
        "sub_features": [
            "Examination Planning", "Hall Ticket Generation",
            "Seating Arrangement", "Invigilator Allocation",
            "Internal Assessment", "CIA Marks",
            "Online Examination", "Offline Examination",
            "Question Bank", "Question Paper Generator",
            "Digital Valuation", "Result Processing",
            "Grade Card", "CGPA Calculation",
            "Transcript Generation", "Consolidated Mark Statement",
            "Revaluation", "Supplementary Examination",
            "Degree Audit", "Result Analytics",
        ],
        "default_price_per_student": Decimal("70"),
    },
    "CMS_FEES_FINANCE": {
        "code": "CMS_FEES_FINANCE",
        "name": "Fees & Finance",
        "category": "CMS_FINANCE",
        "icon": "💰",
        "color": "#2E7D32",
        "short_desc": "Fee structures to financial reports - collections, ledgers, reconciliation.",
        "sub_features": [
            "Fee Structure", "Fee Collection",
            "Online Payments", "Scholarship Management",
            "Concessions", "Installments",
            "Fine Calculation", "Refund Management",
            "Receipts", "Ledger",
            "Income & Expense", "Budget Management",
            "Bank Reconciliation", "Financial Reports",
        ],
        "default_price_per_student": Decimal("45"),
    },
    "CMS_HRM": {
        "code": "CMS_HRM",
        "name": "HR and Payroll",
        "category": "CMS_FINANCE",
        "icon": "👥",
        "color": "#E65100",
        "short_desc": "Recruitment to payroll - the full employee lifecycle in one place.",
        "sub_features": [
            "Employee Management", "Recruitment",
            "Staff Profile", "Leave Management",
            "Attendance", "Payroll",
            "Salary Processing", "Increment Management",
            "Appraisal", "Performance Review",
            "Employee Self-Service", "HR Analytics",
        ],
        "default_price_per_student": Decimal("45"),
    },
    "CMS_LIBRARY": {
        "code": "CMS_LIBRARY",
        "name": "Library Management",
        "category": "CMS_STUDENT",
        "icon": "📖",
        "color": "#6A1B9A",
        "short_desc": "OPAC, barcode circulation, digital library and journals.",
        "sub_features": [
            "OPAC", "Barcode Support",
            "Book Issue & Return", "Digital Library",
            "E-Books", "Journal Management",
            "Subscription Management", "Fine Calculation",
            "Library Reports",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "CMS_HOSTEL_MESS": {
        "code": "CMS_HOSTEL_MESS",
        "name": "Hostel & Mess Management",
        "category": "CMS_STUDENT",
        "icon": "🏠",
        "color": "#00838F",
        "short_desc": "Rooms, gate passes, mess planning and billing - fully tracked.",
        "sub_features": [
            "Hostel Admission", "Room Allocation",
            "Bed Management", "Visitor Management",
            "Gate Pass", "Leave Management",
            "Mess Attendance", "Menu Planning",
            "Recipe Management", "Inventory",
            "Mess Billing", "Hostel Analytics",
        ],
        "default_price_per_student": Decimal("35"),
    },
    "CMS_TRANSPORT": {
        "code": "CMS_TRANSPORT",
        "name": "Transport Management",
        "category": "CMS_STUDENT",
        "icon": "🚌",
        "color": "#C62828",
        "short_desc": "Vehicles, routes, drivers and transport fees under control.",
        "sub_features": [
            "Vehicle Management", "Route Planning",
            "Boarding Points", "Driver Management",
            "Fuel Tracking", "Vehicle Maintenance",
            "Student Transport Allocation", "Transport Fee Collection",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "CMS_PLACEMENT": {
        "code": "CMS_PLACEMENT",
        "name": "Placement & Career Services",
        "category": "CMS_STUDENT",
        "icon": "💼",
        "color": "#283593",
        "short_desc": "Campus drives, eligibility, offers and placement analytics.",
        "sub_features": [
            "Company Registration", "Campus Drives",
            "Student Eligibility", "Resume Management",
            "Interview Scheduling", "Placement Tracking",
            "Offer Management", "Alumni Referrals",
            "Placement Analytics",
        ],
        "default_price_per_student": Decimal("30"),
    },
    "CMS_ALUMNI": {
        "code": "CMS_ALUMNI",
        "name": "Alumni Management",
        "category": "CMS_STUDENT",
        "icon": "🤝",
        "color": "#1565C0",
        "short_desc": "A living alumni network - directory, events, donations, mentorship.",
        "sub_features": [
            "Alumni Registration", "Alumni Portal",
            "Alumni Directory", "Events",
            "Donations", "Networking",
            "Mentorship",
        ],
        "default_price_per_student": Decimal("20"),
    },
    "CMS_RESEARCH": {
        "code": "CMS_RESEARCH",
        "name": "Research & Innovation",
        "category": "CMS_CORE",
        "icon": "🔬",
        "color": "#2E7D32",
        "short_desc": "Publications, patents, funded projects and FDPs - tracked institution-wide.",
        "sub_features": [
            "Publications", "Patents",
            "Consultancy", "Funded Projects",
            "Journals", "Conferences",
            "FDP", "Workshops",
            "Faculty Research", "Student Research",
        ],
        "default_price_per_student": Decimal("30"),
    },
    "CMS_COMPLIANCE": {
        "code": "CMS_COMPLIANCE",
        "name": "NAAC / NBA / NIRF / IQAC",
        "category": "CMS_CORE",
        "icon": "✅",
        "color": "#E65100",
        "short_desc": "Accreditation reports on demand - SSR, AQAR, NIRF, IQAC.",
        "sub_features": [
            "SSR Data Collection", "Criteria-wise Reports",
            "AQAR Reports", "DVV Support",
            "AISHE Reports", "NIRF Data",
            "IQAC Documentation", "Academic Audit",
            "Department Audit", "Compliance Dashboard",
        ],
        "default_price_per_student": Decimal("40"),
    },
    "CMS_INVENTORY": {
        "code": "CMS_INVENTORY",
        "name": "Inventory & Asset Management",
        "category": "CMS_FINANCE",
        "icon": "📦",
        "color": "#6A1B9A",
        "short_desc": "Purchases, assets, AMC and stores - audited end to end.",
        "sub_features": [
            "Purchase Request", "Purchase Order",
            "Vendor Management", "Asset Register",
            "Stock Management", "AMC Tracking",
            "Asset Maintenance", "Store Management",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "CMS_COMMUNICATION": {
        "code": "CMS_COMMUNICATION",
        "name": "Communication Hub",
        "category": "CMS_STUDENT",
        "icon": "📣",
        "color": "#00838F",
        "short_desc": "SMS, WhatsApp, email and push - every stakeholder reached instantly.",
        "sub_features": [
            "SMS", "Email",
            "WhatsApp", "Push Notifications",
            "Circulars", "Announcements",
            "Discussion Forum", "Event Calendar",
            "Notice Board",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "CMS_PORTAL": {
        "code": "CMS_PORTAL",
        "name": "Student & Parent Portal",
        "category": "CMS_STUDENT",
        "icon": "🌐",
        "color": "#C62828",
        "short_desc": "Self-service for students and real-time visibility for parents.",
        "sub_features": [
            "View Attendance", "View Results",
            "Pay Fees", "Download Hall Ticket",
            "Download Certificates", "View Timetable",
            "Apply Leave", "Submit Assignments",
            "Register Grievance", "Hostel Request",
            "Library Access", "Monitor Attendance (Parents)",
            "Academic Progress (Parents)", "Fee Status (Parents)",
            "Notifications (Parents)", "Communication with Faculty (Parents)",
        ],
        "default_price_per_student": Decimal("35"),
    },
    "CMS_FACULTY_PORTAL": {
        "code": "CMS_FACULTY_PORTAL",
        "name": "Faculty Portal",
        "category": "CMS_CORE",
        "icon": "👨‍🏫",
        "color": "#283593",
        "short_desc": "Everything faculty need daily - attendance, marks, plans, leave.",
        "sub_features": [
            "Attendance Entry", "Lesson Plan",
            "Internal Marks", "Assignment Evaluation",
            "Timetable", "Student Performance",
            "Leave Request", "Research Profile",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "CMS_MOBILE": {
        "code": "CMS_MOBILE",
        "name": "Mobile Applications",
        "category": "CMS_STUDENT",
        "icon": "📱",
        "color": "#1565C0",
        "short_desc": "Android & iOS apps for students, faculty, parents and management.",
        "sub_features": [
            "Android & iOS", "Student App",
            "Faculty App", "Parent App",
            "Management App", "Push Notifications",
            "Digital ID Card", "Online Payments",
            "Attendance", "Results",
        ],
        "default_price_per_student": Decimal("40"),
    },
    "CMS_DASHBOARDS": {
        "code": "CMS_DASHBOARDS",
        "name": "Dashboards & Analytics",
        "category": "CMS_CORE",
        "icon": "📊",
        "color": "#2E7D32",
        "short_desc": "Role-based dashboards with live KPIs and exportable reports.",
        "sub_features": [
            "Management Dashboard", "Principal Dashboard",
            "HOD Dashboard", "COE Dashboard",
            "Finance Dashboard", "HR Dashboard",
            "Placement Dashboard", "Real-time KPIs",
            "Interactive Charts", "Custom Reports",
            "Excel/PDF Export",
        ],
        "default_price_per_student": Decimal("35"),
    },
    "CMS_INTEGRATION": {
        "code": "CMS_INTEGRATION",
        "name": "Integration",
        "category": "CMS_CORE",
        "icon": "🔗",
        "color": "#E65100",
        "short_desc": "Payment, SMS, WhatsApp, biometrics, Google/Microsoft, REST APIs and SSO - connected.",
        "sub_features": [
            "Payment Gateway", "SMS Gateway",
            "WhatsApp Integration", "Email Integration",
            "Face / Thumb Reader (Biometric)", "Google Workspace",
            "Microsoft 365", "REST APIs",
            "ERP Integration", "Single Sign-On (SSO)",
        ],
        "default_price_per_student": Decimal("30"),
    },
    "CMS_SECURITY": {
        "code": "CMS_SECURITY",
        "name": "Security & Administration",
        "category": "CMS_CORE",
        "icon": "🔐",
        "color": "#6A1B9A",
        "short_desc": "RBAC, encryption, backups and multi-campus administration.",
        "sub_features": [
            "Role-Based Access Control (RBAC)", "Multi-Campus Management",
            "Multi-Institution Support", "Audit Logs",
            "Data Encryption", "Automatic Backup",
            "Disaster Recovery", "Two-Factor Authentication",
            "Cloud Deployment", "On-Premise Deployment",
            "API Security",
        ],
        "default_price_per_student": Decimal("35"),
    },

    # ============================ COE - 13 sub-modules =====================
    "COE_MASTER_SETUP": {
        "code": "COE_MASTER_SETUP",
        "name": "Examination Master Setup",
        "category": "COE_CORE",
        "icon": "⚙️",
        "color": "#1565C0",
        "short_desc": "Regulation, curriculum, course master and academic year configuration.",
        "sub_features": [
            "Regulation management",
            "Curriculum & scheme",
            "Course master",
            "Subject mapping",
            "Examination calendar",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_REGISTRATION": {
        "code": "COE_REGISTRATION",
        "name": "Student Examination Registration",
        "category": "COE_CORE",
        "icon": "📝",
        "color": "#2E7D32",
        "short_desc": "Regular & arrear registration with fee and eligibility verification.",
        "sub_features": [
            "Regular registration",
            "Arrear registration",
            "Fee verification",
            "Eligibility verification",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_HALL_TICKET": {
        "code": "COE_HALL_TICKET",
        "name": "Hall Ticket Management",
        "category": "COE_CORE",
        "icon": "🎫",
        "color": "#E65100",
        "short_desc": "Auto hall ticket generation with QR verification and portal download.",
        "sub_features": [
            "Auto generation",
            "QR code verification",
            "Department-wise tickets",
            "Student portal download",
        ],
        "default_price_per_student": Decimal("10"),
    },
    "COE_QUESTION_PAPER": {
        "code": "COE_QUESTION_PAPER",
        "name": "Question Paper Management",
        "category": "COE_CORE",
        "icon": "📄",
        "color": "#1565C0",
        "short_desc": "Repository, approval workflow and confidential access control.",
        "sub_features": [
            "Question paper repository",
            "Approval workflow",
            "Confidential access control",
            "Secure download",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_INTERNAL_ASSESSMENT": {
        "code": "COE_INTERNAL_ASSESSMENT",
        "name": "Internal Assessment Management",
        "category": "COE_CORE",
        "icon": "📊",
        "color": "#2E7D32",
        "short_desc": "CIA marks, attendance, assignments with moderation and approval.",
        "sub_features": [
            "CIA marks entry",
            "Attendance marks",
            "Assignment marks",
            "Moderation process",
            "Department approval",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_EXTERNAL_EXAM": {
        "code": "COE_EXTERNAL_EXAM",
        "name": "External Examination Management",
        "category": "COE_CORE",
        "icon": "🏛️",
        "color": "#E65100",
        "short_desc": "Seating, hall allocation, invigilator allocation and malpractice tracking.",
        "sub_features": [
            "Seating arrangement",
            "Hall allocation",
            "Invigilator allocation",
            "Attendance entry",
            "Malpractice tracking",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_DIGITAL_VALUATION": {
        "code": "COE_DIGITAL_VALUATION",
        "name": "Digital Valuation System",
        "category": "COE_RESULTS",
        "icon": "🖥️",
        "color": "#1565C0",
        "short_desc": "On-screen evaluation with double valuation and moderation tracking.",
        "sub_features": [
            "Examiner allocation",
            "On-screen evaluation",
            "Mark entry",
            "Double valuation",
            "Valuation tracking dashboard",
        ],
        "default_price_per_student": Decimal("25"),
    },
    "COE_RESULT_PROCESSING": {
        "code": "COE_RESULT_PROCESSING",
        "name": "Result Processing",
        "category": "COE_RESULTS",
        "icon": "📈",
        "color": "#2E7D32",
        "short_desc": "Grade, GPA/CGPA calculation with approval workflow and publication.",
        "sub_features": [
            "Grade calculation",
            "GPA / CGPA calculation",
            "Approval workflow",
            "Result publication",
            "Department-wise analysis",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_REVALUATION": {
        "code": "COE_REVALUATION",
        "name": "Revaluation & Retotalling",
        "category": "COE_RESULTS",
        "icon": "🔄",
        "color": "#E65100",
        "short_desc": "Student application portal with fee collection and workflow.",
        "sub_features": [
            "Student application portal",
            "Fee collection integration",
            "Revaluation workflow",
            "Revised result processing",
        ],
        "default_price_per_student": Decimal("10"),
    },
    "COE_SUPPLEMENTARY": {
        "code": "COE_SUPPLEMENTARY",
        "name": "Supplementary Examination Management",
        "category": "COE_RESULTS",
        "icon": "♻️",
        "color": "#1565C0",
        "short_desc": "Arrear exam registration, hall ticket and result processing.",
        "sub_features": [
            "Arrear exam registration",
            "Hall ticket generation",
            "Result processing",
        ],
        "default_price_per_student": Decimal("10"),
    },
    "COE_TRANSCRIPT": {
        "code": "COE_TRANSCRIPT",
        "name": "Transcript & Certificate Management",
        "category": "COE_RESULTS",
        "icon": "📜",
        "color": "#2E7D32",
        "short_desc": "Grade sheets, consolidated mark statements and transcripts.",
        "sub_features": [
            "Grade sheet generation",
            "Consolidated mark statement",
            "Transcript generation",
            "Provisional certificate",
            "Duplicate certificate processing",
        ],
        "default_price_per_student": Decimal("15"),
    },
    "COE_STUDENT_PORTAL": {
        "code": "COE_STUDENT_PORTAL",
        "name": "Student Self-Service Portal",
        "category": "COE_CORE",
        "icon": "👤",
        "color": "#E65100",
        "short_desc": "Exam registration, hall ticket download, result view, transcript request.",
        "sub_features": [
            "Exam registration",
            "Hall ticket download",
            "Result view",
            "Revaluation application",
            "Transcript request",
        ],
        "default_price_per_student": Decimal("10"),
    },
    "COE_ANALYTICS": {
        "code": "COE_ANALYTICS",
        "name": "Examination Analytics & Reports",
        "category": "COE_RESULTS",
        "icon": "📊",
        "color": "#1565C0",
        "short_desc": "Pass percentage, subject-wise, accreditation-ready reports.",
        "sub_features": [
            "Pass percentage analysis",
            "Subject-wise analysis",
            "University submission reports",
            "Accreditation reports",
        ],
        "default_price_per_student": Decimal("10"),
    },

    # ============================ Add-ons ===================================
    "COPO_MAPPING": {
        "code": "COPO_MAPPING",
        "name": "CO–PO Mapping Module",
        "category": "ADDON",
        "icon": "🎁",
        "color": "#2E7D32",
        "short_desc": "Ensures OBE compliance by mapping COs with POs and PSOs as per NBA/NAAC.",
        "sub_features": [
            "CO definition & management",
            "PO & PSO configuration",
            "CO–PO mapping matrix",
            "Attainment calculation",
            "Target & threshold settings",
            "Indirect assessment integration",
            "Gap analysis & continuous improvement",
        ],
        "default_price_per_student": Decimal("0"),
        "tag": "FREE",
    },

    # ============================ Standalone offerings =====================
    "STD_HR_PAYROLL": {
        "code": "STD_HR_PAYROLL",
        "name": "HR & Payroll (Standalone)",
        "category": "STANDALONE",
        "icon": "💼",
        "color": "#2E7D32",
        "short_desc": "Full HR + payroll suite - usable without the rest of CMS.",
        "sub_features": [
            "Employee lifecycle",
            "Biometric attendance",
            "Leave management",
            "Salary structure & payslips",
            "PF / ESI / PT / IT statutory",
            "Form-16 generation",
        ],
        "default_price_per_student": Decimal("120"),
        "one_time_fee": Decimal("150000"),
    },
}


# ---------------------------------------------------------------------------
# Bundles - pre-built packages
# ---------------------------------------------------------------------------
def _sum_modules(codes: list[str]) -> Decimal:
    return sum((MODULES[c]["default_price_per_student"] for c in codes), Decimal("0"))


# Order matches the canonical proposal document (modules 01-25).
CMS_FULL_MODULES = [
    "CMS_ADMISSION", "CMS_SIS", "CMS_ACADEMIC", "CMS_OBE",
    "CMS_ATTENDANCE", "CMS_TIMETABLE", "CMS_LMS", "CMS_EXAMINATION",
    "CMS_FEES_FINANCE", "CMS_HRM", "CMS_LIBRARY", "CMS_HOSTEL_MESS",
    "CMS_TRANSPORT", "CMS_PLACEMENT", "CMS_ALUMNI", "CMS_RESEARCH",
    "CMS_COMPLIANCE", "CMS_INVENTORY", "CMS_COMMUNICATION", "CMS_PORTAL",
    "CMS_FACULTY_PORTAL", "CMS_MOBILE", "CMS_DASHBOARDS",
    "CMS_INTEGRATION", "CMS_SECURITY",
]

# Total feature count across the CMS bundle - drives the hero "275+" stat
# so the number can never drift from the actual catalog.
def _cms_feature_count() -> int:
    return sum(len(MODULES[c].get("sub_features", [])) for c in CMS_FULL_MODULES)

COE_FULL_MODULES = [
    "COE_MASTER_SETUP", "COE_REGISTRATION", "COE_HALL_TICKET",
    "COE_QUESTION_PAPER", "COE_INTERNAL_ASSESSMENT", "COE_EXTERNAL_EXAM",
    "COE_DIGITAL_VALUATION", "COE_RESULT_PROCESSING", "COE_REVALUATION",
    "COE_SUPPLEMENTARY", "COE_TRANSCRIPT", "COE_STUDENT_PORTAL",
    "COE_ANALYTICS",
]


BUNDLES: dict[str, Bundle] = {

    "CMS_FULL": {
        "code": "CMS_FULL",
        "name": "Complete CMS ERP",
        "tagline": "All 25 integrated modules - one ecosystem for the whole institution.",
        "modules": CMS_FULL_MODULES,
        "bundle_price_per_student": Decimal("500"),
        "standalone_total": _sum_modules(CMS_FULL_MODULES),
        "one_time_implementation_fee": Decimal("500000"),
        "waive_one_time_default": True,
        "hero_color": "#1565C0",
        "hero_gradient_end": "#E65100",
    },

    "COE_FULL": {
        "code": "COE_FULL",
        "name": "Complete COE Suite",
        "tagline": "End-to-end examination lifecycle - registration to transcripts.",
        "modules": COE_FULL_MODULES + ["COPO_MAPPING"],
        "bundle_price_per_student": Decimal("150"),
        "standalone_total": _sum_modules(COE_FULL_MODULES),
        "one_time_implementation_fee": Decimal("500000"),
        "waive_one_time_default": True,
        "hero_color": "#1565C0",
        "hero_gradient_end": "#2E7D32",
    },

    "COE_CLASSIC": {
        "code": "COE_CLASSIC",
        "name": "COE Package (Classic Pricing)",
        "tagline": "Same COE suite, classic per-student/per-year pricing.",
        "modules": COE_FULL_MODULES,
        "bundle_price_per_student": Decimal("250"),
        "standalone_total": _sum_modules(COE_FULL_MODULES),
        "one_time_implementation_fee": Decimal("500000"),
        "waive_one_time_default": True,
        "hero_color": "#1a3c6e",
        "hero_gradient_end": "#1a3c6e",
    },

    "HR_PAYROLL_STANDALONE": {
        "code": "HR_PAYROLL_STANDALONE",
        "name": "HR & Payroll (Standalone)",
        "tagline": "Plug-and-play HR + payroll for institutions not ready for full ERP.",
        "modules": ["STD_HR_PAYROLL"],
        "bundle_price_per_student": Decimal("120"),
        "standalone_total": MODULES["STD_HR_PAYROLL"]["default_price_per_student"],
        "one_time_implementation_fee": Decimal("150000"),
        "waive_one_time_default": False,
        "hero_color": "#2E7D32",
        "hero_gradient_end": "#1565C0",
    },
}


# ---------------------------------------------------------------------------
# Per-bundle presentation defaults (hero copy, stats, phases, terms)
# Keeps all narrative content in one place - the view stays thin.
# ---------------------------------------------------------------------------
DEFAULT_PHASES: list[dict] = [
    {"title": "Discovery & Requirement Gathering",
     "desc": "Deep-dive into your workflows to identify challenges and needs.",
     "duration": "1 Week", "color": "#1565C0"},
    {"title": "Configuration & Customization",
     "desc": "Tailor modules for an optimized fit to your operational model.",
     "duration": "2 Weeks", "color": "#2E7D32"},
    {"title": "Data Migration & Integration",
     "desc": "Securely migrate existing records and integrate third-party APIs.",
     "duration": "1 Week", "color": "#E65100"},
    {"title": "Training & Rollout",
     "desc": "Equip your team with in-depth training for a confident go-live.",
     "duration": "3 Days", "color": "#1565C0"},
    {"title": "Post-Implementation Excellence",
     "desc": "Regular updates and proactive support to keep your institution future-ready.",
     "duration": "Ongoing", "color": "#2E7D32"},
]


DEFAULT_TERMS: list[str] = [
    "GST (18%) extra.",
    "50% of payment as advance. Remaining after implementation & training.",
    "100% advance payment from second year onwards.",
    "Data collection has to be provided by the client in the given template by "
    "the accepted timeline. Any delay in data collection will not reflect in "
    "the payment period.",
    "All sign-offs (Training / Go-live) have to be completed within 15 working "
    "days, otherwise they will be considered as signed off.",
    "The implementation plan will be sent by Aveon after our sign-off. This "
    "will be discussed with the client & fixed. Both sides must follow it to "
    "complete the implementation as on date.",
    "Online support will be free of cost.",
    "Client has to provide SMS / WhatsApp API credentials for integration.",
    "The license fee shall remain fixed for the first two years. 5% increase "
    "on the license price will be applied every year from the beginning of "
    "the third year.",
]


# ---------------------------------------------------------------------------
# Narrative content for the proposal sections - verbatim style from the
# canonical Aveon HTML proposals so the rendered output matches in format,
# alignment and tone.
# ---------------------------------------------------------------------------
FIVE_PILLARS: list[dict] = [
    {"title": "Comprehensive Integration",
     "desc": "All institutional functions in one unified platform - no more silos.",
     "color": "#1565C0", "icon": "🔗"},
    {"title": "Future-Ready Technology",
     "desc": "Modern architecture built to scale with your institution's growth.",
     "color": "#2E7D32", "icon": "🚀"},
    {"title": "Compliance Built-In",
     "desc": "Aligned with NAAC, NBA, NIRF, AICTE and UGC standards out of the box.",
     "color": "#E65100", "icon": "✅"},
    {"title": "User-Centric Design",
     "desc": "Intuitive interfaces for management, staff, students and parents alike.",
     "color": "#1565C0", "icon": "🎨"},
    {"title": "Trusted Partnership",
     "desc": "A decade of delivering ERP solutions for educational institutions.",
     "color": "#2E7D32", "icon": "🤝"},
]


BENEFITS: list[dict] = [
    {"title": "For Management",
     "icon": "🏛️", "color": "#1565C0",
     "items": [
        "Instant access to actionable insights for strategic decision-making.",
        "A unified platform that minimizes silos and maximizes efficiency.",
        "Audit-ready compliance data available on demand.",
     ]},
    {"title": "For Educators & Staff",
     "icon": "👨‍🏫", "color": "#2E7D32",
     "items": [
        "Reduced administrative burden - more time for teaching and mentoring.",
        "Tools for better academic planning and student engagement.",
        "Attendance, marks and lesson plans in a single click.",
     ]},
    {"title": "For Students & Parents",
     "icon": "🎓", "color": "#E65100",
     "items": [
        "Transparency in academic progress and fees builds trust.",
        "Always-connected mobile apps keep everyone informed.",
        "Self-service for results, certificates, payments and requests.",
     ]},
]


IMPLEMENTATION_COMPONENTS: list[dict] = [
    {"title": "Requirement Analysis & Consultation",
     "desc": "Detailed discussions with stakeholders to understand institutional workflows of all modules."},
    {"title": "Software Customization",
     "desc": "Tailoring modules to meet the unique needs of the institution (e.g., CBCS, OBE, fee structures, reports, etc.)."},
    {"title": "Data Migration",
     "desc": "Importing legacy data - student records, staff, library, inventory, asset management, vendor data, COE data, financial data. Complete cleansing and validation."},
    {"title": "System Configuration",
     "desc": "Role-based access for management, administrators, staff, students, parents. Defining workflows and automation rules across all modules."},
    {"title": "Hosting and Deployment",
     "desc": "Setting up the solution on on-premise server based on the client preference. Daily auto-backup configuration."},
    {"title": "Integration Services",
     "desc": "SMS, WhatsApp, email and payment gateway integration. Biometric/face-reader devices and smart cards for attendance. Third-party tool integrations."},
    {"title": "User Training",
     "desc": "Comprehensive training sessions for administrators, staff and faculty. Creation of user manuals and training guides."},
    {"title": "Testing and Quality Assurance",
     "desc": "Rigorous testing to ensure all modules work seamlessly. UAT to confirm readiness for launch."},
    {"title": "Go-Live Support",
     "desc": "On-site or remote support during the go-live phase. Addressing any immediate concerns or configurations."},
    {"title": "Initial Report Customization",
     "desc": "Development of essential reports as requested by the client (e.g., student performance, fee collection summaries). Free for the first year."},
    {"title": "Mobile App Configuration",
     "desc": "Initial setup of mobile applications for staff, students and parents."},
    {"title": "Post-Implementation Support",
     "desc": "Free support to address early-stage queries or issues after go-live."},
]


WHY_AVEON: list[dict] = [
    {"title": "Proven Expertise",
     "desc": "A decade of excellence in delivering tailored ERP solutions for educational institutions."},
    {"title": "Client-Centric Approach",
     "desc": "Personalized service to align with your institutional goals and workflow."},
    {"title": "Scalable and Secure",
     "desc": "Built to grow with your needs while ensuring data integrity and access control."},
    {"title": "Unparalleled Support",
     "desc": "A dedicated team for ongoing assistance, updates and continuous improvement."},
]


# ---------------------------------------------------------------------------
# "Why Now" narrative - the challenge/opportunity story that opens the
# proposal, with the before/after comparison. Copy from the canonical
# Aveon CMS ERP proposal document.
# ---------------------------------------------------------------------------
WHY_NOW: dict = {
    "challenge": (
        "Running a modern institution means juggling admissions, academics, "
        "exams, fees, HR, hostel, transport, placements and accreditation - "
        "often across disconnected spreadsheets and half a dozen standalone "
        "tools. The cost shows up everywhere: the same data keyed in three "
        "times, decisions delayed while reports are compiled by hand, a "
        "scramble every time NAAC or NBA comes calling and skilled staff "
        "buried in routine paperwork instead of teaching and mentoring."
    ),
    "opportunity": (
        "Aveon's Complete CMS ERP replaces that patchwork with one connected "
        "platform. Every record is entered once and shared everywhere. "
        "Attendance, marks and fees are captured automatically. Leadership "
        "sees live dashboards instead of month-old summaries. Parents and "
        "students stay informed through mobile apps. And accreditation "
        "reports are generated on demand - not assembled in a panic."
    ),
    "bottom_line": (
        "The bottom line: one source of truth, up to 90% less manual effort "
        "and the real-time intelligence to run your institution with "
        "confidence."
    ),
}

BEFORE_AFTER: list[tuple[str, str]] = [
    ("Data scattered across spreadsheets & apps",
     "A single source of truth across 25 modules"),
    ("Attendance, marks & fees keyed in by hand",
     "Automated capture with instant notifications"),
    ("Audit prep takes weeks of scrambling",
     "NAAC / NBA / NIRF reports generated on demand"),
    ("Parents chase staff for every update",
     "Real-time visibility through mobile apps"),
    ("Leadership decides on stale data",
     "Live dashboards & KPIs, updated continuously"),
]

NEXT_STEPS: list[dict] = [
    {"title": "Book a Free Demo",
     "desc": "See the platform on your own workflows."},
    {"title": "Confirm & Sign Off",
     "desc": "Approve scope and lock your timeline."},
    {"title": "Go Live in 5-6 Weeks",
     "desc": "We migrate, train and launch with you."},
]

SALUTATION: str = (
    "Thank you for the opportunity to present Aveon's Complete CMS ERP. "
    "This proposal shows exactly how your institution can unify admissions, "
    "academics, examinations, finance, HR and compliance on a single modern "
    "platform - and go live in as little as five to six weeks."
)


PRESENTATIONS: dict[str, dict] = {
    "CMS_FULL": {
        "kicker": "Complete CMS ERP",
        "title_template": "Run Your Entire <em>Campus</em> on One Platform",
        "subtitle": (f"From admissions to alumni - {len(CMS_FULL_MODULES)} "
                     "integrated modules, one login, zero silos. Purpose-built "
                     "for the modern Indian institution."),
        "stats_template": [
            {"value": str(len(CMS_FULL_MODULES)), "label": "Integrated Modules"},
            {"value": f"{_cms_feature_count()}+", "label": "Features Included"},
            {"value": "90%", "label": "Manual Effort Saved"},
            {"value": "5-6", "label": "Weeks to Go-Live"},
        ],
        "executive_title": "Streamline Your Institution's Operations",
        "executive_paragraphs": [
            "Aveon Infotech proposes the implementation of our Complete CMS ERP at {client}, transforming how you manage academic, administrative and financial operations.",
            "The solution covers the entire institutional lifecycle - admissions, academics, attendance, examinations, finance, HR & payroll, library, hostel, transport, placements, alumni, research, accreditation and analytics - in one unified platform.",
            "It is designed to reduce manual effort, improve accuracy, accelerate decision-making and give every stakeholder real-time institutional intelligence.",
        ],
        "modules_section_title": f"{len(CMS_FULL_MODULES)} Integrated Modules",
        "modules_section_desc": "A complete ecosystem covering every dimension of institutional management - from admissions to alumni. Each module below lists the features included at no extra cost.",
        "commercial_line_label": "Complete CMS ERP Package - all 25 modules - Per Student / Per Year",
    },
    "COE_FULL": {
        "kicker": "Complete COE Suite",
        "title_template": "End-to-end <em>Examination</em> Automation for {client}",
        "subtitle": ("Streamline the entire examination lifecycle - from "
                     "registration to transcripts - with built-in NBA/NAAC "
                     "compliance."),
        "stats_template": [
            {"value": "13+1", "label": "Modules + Free CO-PO Add-on"},
            {"value": "5-6", "label": "Weeks to Go-Live"},
            {"value": "Free", "label": "CO-PO Mapping Add-on"},
        ],
        "executive_title": "Redefining Examination Management",
        "executive_paragraphs": [
            "Aveon Infotech proposes the Aveon Controller of Examinations (COE) Automation System to streamline and digitise the complete examination lifecycle at {client}.",
            "The proposed solution automates examination planning, student registration, hall ticket generation, valuation, result processing, revaluation, supplementary examinations, transcript generation and statutory reports - while ensuring compliance with university regulations and institutional academic policies.",
            "The system is designed to reduce manual effort, improve accuracy, accelerate result publication and provide real-time examination analytics.",
        ],
        "modules_section_title": "14 Fully Integrated COE Modules",
        "modules_section_desc": "End-to-end examination automation - every step from regulation setup to transcript generation, including a free CO–PO Mapping add-on.",
        "commercial_line_label": "Annual Subscription Fee for Complete COE Module - Per Student Per Year",
        "commercial_bonus_label": "🎁 CO–PO Mapping Module included FREE as add-on (worth ₹75 per student per year)",
    },
    "COE_CLASSIC": {
        "kicker": "COE Package",
        "title_template": "<em>Examination Automation</em> for {client}",
        "subtitle": ("End-to-end COE suite with classic per-student, "
                     "per-year subscription pricing."),
        "stats_template": [
            {"value": "13", "label": "COE Modules"},
            {"value": "5-6", "label": "Weeks to Go-Live"},
            {"value": "Annual", "label": "Per-Student Subscription"},
        ],
        "executive_title": "Examination Automation, Made Simple",
        "executive_paragraphs": [
            "Aveon Infotech proposes the implementation of the Aveon Controller of Examinations (COE) Automation System at {client}, covering the complete examination lifecycle.",
            "From regulation management and registration through hall tickets, valuation, results, revaluation and transcripts - every stage is automated, audited and accreditation-ready.",
            "Designed to reduce administrative workload, accelerate result publication and improve transparency for students, parents and management.",
        ],
        "modules_section_title": "13 Integrated COE Modules",
        "modules_section_desc": "Complete examination lifecycle automation aligned with university regulations.",
        "commercial_line_label": "Complete COE Package - Per Student / Per Year",
    },
    "HR_PAYROLL_STANDALONE": {
        "kicker": "HR & Payroll Standalone",
        "title_template": "Plug-and-Play <em>HR & Payroll</em> for {client}",
        "subtitle": ("Full HR + payroll suite - usable without the rest of "
                     "the CMS ecosystem."),
        "stats_template": [
            {"value": "6+", "label": "HR Workflows"},
            {"value": "3-4", "label": "Weeks to Go-Live"},
            {"value": "100%", "label": "Statutory Compliance"},
        ],
        "executive_title": "End-to-End HR & Payroll Automation",
        "executive_paragraphs": [
            "Aveon Infotech proposes a complete HR & Payroll automation solution for {client}, covering employee lifecycle, attendance, leave, payroll and statutory compliance - without requiring the full CMS ecosystem.",
            "The system automates salary computation, statutory deductions (PF, ESI, PT, IT), Form-16 generation, biometric attendance integration and full payslip distribution.",
            "Designed to be plug-and-play for institutions that need HR & Payroll automation today and may scale to full ERP later.",
        ],
        "modules_section_title": "HR & Payroll Workflows",
        "modules_section_desc": "Employee lifecycle to payslip - fully automated with statutory compliance built in.",
        "commercial_line_label": "HR & Payroll Subscription - Per Employee / Per Year",
    },
}

# Fallback for CUSTOM-mode proposals (no bundle code).
CUSTOM_PRESENTATION: dict = {
    "kicker": "Custom Stack",
    "title_template": "Custom <em>Modular Stack</em> for {client}",
    "subtitle": ("A curated combination of Aveon modules - picked to match "
                 "your institution's specific workflow needs."),
    "stats_template": None,  # generated dynamically in build_presentation()
}


def build_presentation(
    *,
    bundle_code: str | None,
    modules: list[Module],
    client_name: str,
    hero_color_override: str | None = None,
    hero_gradient_override: str | None = None,
) -> dict:
    """
    Returns a `hero` dict + `hero_stats` list suitable for the templates.

    For bundle mode, copy is pulled from PRESENTATIONS. For custom mode,
    stats are generated from the module list itself.
    """
    if bundle_code and bundle_code in BUNDLES:
        bundle = BUNDLES[bundle_code]
        pres = PRESENTATIONS.get(bundle_code, CUSTOM_PRESENTATION)
        hero = {
            "color": hero_color_override or bundle["hero_color"],
            "gradient_end": hero_gradient_override or bundle["hero_gradient_end"],
            "kicker": pres["kicker"],
            "title": pres["title_template"].format(client=client_name),
            "subtitle": pres["subtitle"],
        }
        stats = pres["stats_template"]
    else:
        pres = CUSTOM_PRESENTATION
        hero = {
            "color": hero_color_override or "#1565C0",
            "gradient_end": hero_gradient_override or "#E65100",
            "kicker": pres["kicker"],
            "title": pres["title_template"].format(client=client_name),
            "subtitle": pres["subtitle"],
        }
        stats = [
            {"value": str(len(modules)), "label": "Modules Selected"},
            {"value": "5-6", "label": "Weeks to Go-Live"},
            {"value": "Tailored", "label": "Per Institution"},
        ]
    return {"hero": hero, "hero_stats": stats}


# ---------------------------------------------------------------------------
# Helpers used by the form / view
# ---------------------------------------------------------------------------
def module_choices() -> list[tuple[str, str]]:
    """Choices for the MultipleChoiceField, grouped by category label."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for code, mod in MODULES.items():
        grouped.setdefault(mod["category"], []).append((code, mod["name"]))
    out: list[tuple[str, str]] = []
    for cat_code, cat_label in CATEGORIES.items():
        items = grouped.get(cat_code, [])
        if not items:
            continue
        out.append((cat_label, items))  # Django supports grouped choices
    return out


def bundle_choices() -> list[tuple[str, str]]:
    return [(code, b["name"]) for code, b in BUNDLES.items()]


def resolve_selection(
    *,
    selection_mode: str,
    bundle_code: str | None,
    module_codes: list[str] | None,
) -> list[Module]:
    """Turn form input into a concrete list of modules to render."""
    if selection_mode == "BUNDLE" and bundle_code:
        codes = BUNDLES[bundle_code]["modules"]
    else:
        codes = module_codes or []
    return [MODULES[c] for c in codes if c in MODULES]


def compute_pricing(
    *,
    bundle_code: str | None,
    price_per_unit: Decimal,
    minimum_student_commitment: int,
    one_time_implementation_fee: Decimal,
    waive_one_time: bool,
    gst_percent: Decimal,
) -> dict:
    """
    Single-price model - the sales team negotiates one per-student/per-employee
    rate (e.g., ₹250, ₹300, ₹500) for the bundle they're proposing. No per-module
    breakdown is shown; the proposal lists the modules as features only.

    Returns the two commercial rows that the originals show:
        1. Annual subscription line  (price × commitment)
        2. One-time setup fee        (struck-through if waived)
    """
    students = max(int(minimum_student_commitment or 0), 0)
    price = Decimal(price_per_unit or 0)
    annual = price * students

    pres = PRESENTATIONS.get(bundle_code or "", CUSTOM_PRESENTATION)
    annual_line = {
        "label": pres.get("commercial_line_label") or "Annual Subscription - Per Unit / Per Year",
        "bonus": pres.get("commercial_bonus_label"),
        "amount": annual,
        "per_unit": price,
    }

    impl_fee = Decimal(one_time_implementation_fee or 0)
    impl_line = {
        "label": ("Server setup, installation, implementation, data migration, "
                  "data cleansing & ERP configuration - Per Institution (One-time)"),
        "amount": Decimal("0") if waive_one_time else impl_fee,
        "original_amount": impl_fee,
        "waived": waive_one_time,
    }

    subtotal = annual_line["amount"] + impl_line["amount"]
    gst = (subtotal * Decimal(gst_percent or 0) / Decimal("100"))
    grand_total = subtotal + gst

    return {
        "annual": annual_line,
        "implementation": impl_line,
        "subtotal": subtotal,
        "gst_percent": Decimal(gst_percent or 0),
        "gst_amount": gst,
        "grand_total": grand_total,
    }
