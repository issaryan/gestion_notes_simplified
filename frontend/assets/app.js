// frontend/assets/app.js
const API_BASE = '/api';
let currentUser = null;

// Éléments UI avec vérification de null
const getUIElements = () => ({
    loginForm: document.querySelector('[data-role="login-form"]'),
    dashboard: document.querySelector('[data-role="dashboard"]'),
    errorDiv: document.querySelector('#errorMsg'),
    logoutBtn: document.querySelector('#logoutBtn'),
    studentName: document.querySelector('#studentName'),
    studentEmail: document.querySelector('#studentEmail'),
    coursesContainer: document.querySelector('#coursesContainer'),
    assignedCourses: document.querySelector('#assignedCourses'),
    gradebookBody: document.querySelector('#gradebookBody'),
    courseSelector: document.querySelector('#courseSelector'),
    reportControls: document.querySelector('#reportControls'),
    classSelector: document.querySelector('#classSelector')
});

let ui = getUIElements();

// Gestion de l'authentification
const auth = {
    async initialize() {
        try {
            currentUser = await this.getCurrentUser();
            await this.updateAuthState();
        } catch (error) {
            console.error('Auth initialization error:', error);
        }
    },

    getToken() {
        return localStorage.getItem('jwt');
    },

    setToken(token) {
        localStorage.setItem('jwt', token);
    },

    clearToken() {
        localStorage.removeItem('jwt');
    },

    async getCurrentUser() {
        try {
            const token = this.getToken();
            if (!token) return null;
            
            const response = await fetch(`${API_BASE}/users/me`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            
            if (!response.ok) throw new Error('Invalid token');
            return await response.json();
        } catch (error) {
            this.clearToken();
            return null;
        }
    },

    async updateAuthState() {
        ui = getUIElements(); // Rafraîchir les éléments UI
        if (currentUser) {
            document.body.classList.add(`role-${currentUser.role}`);
            ui.dashboard?.classList?.remove('hidden');
            ui.loginForm?.classList?.add('hidden');
        } else {
            ui.dashboard?.classList?.add('hidden');
            ui.loginForm?.classList?.remove('hidden');
        }
    }
};

// Utilitaire de requête API
async function apiRequest(url, method = 'GET', body = null) {
    showLoadingSpinner();
    const headers = new Headers({
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.getToken()}`
    });

    try {
        const response = await fetch(`${API_BASE}${url}`, {
            method,
            headers,
            body: body ? JSON.stringify(body) : null
        });

        if (response.status === 401) {
            auth.clearToken();
            window.location.reload();
            return;
        }

        if (!response.ok) {
            const error = await response.text();
            throw new Error(error || 'Erreur serveur');
        }

        return response.headers.get('Content-Type')?.includes('json') 
            ? response.json() 
            : response.blob();
    } catch (error) {
        showError(error.message);
        throw error;
    } finally {
        hideLoadingSpinner();
    }
}

// Gestion des erreurs sécurisée
function showError(message) {
    console.error('Application error:', message);
    
    // Méthode de fallback si errorDiv n'existe pas
    if (!ui.errorDiv) {
        const fallbackDiv = document.createElement('div');
        fallbackDiv.className = 'alert alert-danger sticky-top';
        fallbackDiv.textContent = message;
        document.body.prepend(fallbackDiv);
        setTimeout(() => fallbackDiv.remove(), 5000);
        return;
    }

    ui.errorDiv.textContent = message;
    ui.errorDiv.classList.remove('hidden');
    setTimeout(() => ui.errorDiv.classList.add('hidden'), 5000);
}

// Chargement des données utilisateur
async function loadUserData() {
    try {
        if (!currentUser) return;
        
        switch(currentUser.role) {
            case 'student':
                await loadStudentData();
                break;
            case 'teacher':
                await loadTeacherData();
                break;
            case 'admin':
                await loadAdminData();
                break;
        }
    } catch (error) {
        showError('Erreur de chargement des données');
    }
}

// Fonctions étudiant
async function loadStudentData() {
    const [grades, schedule] = await Promise.all([
        apiRequest('/grades'),
        apiRequest('/schedule')
    ]);
    
    renderGrades(grades);
    renderSchedule(schedule);
    
    if (ui.studentName) {
        ui.studentName.textContent = `${currentUser.prenom} ${currentUser.nom}`;
    }
    if (ui.studentEmail) {
        ui.studentEmail.textContent = currentUser.email;
    }
}

function renderGrades(grades) {
    if (!ui.coursesContainer) return;
    
    ui.coursesContainer.innerHTML = grades.map(grade => `
        <div class="course-card">
            <h4>${grade.subject}</h4>
            <div class="course-meta">
                <span>Note: ${grade.grade}/20</span>
                <span>${new Date(grade.evaluation_date).toLocaleDateString()}</span>
            </div>
            ${grade.comments ? `<div class="grade-display">${grade.comments}</div>` : ''}
        </div>
    `).join('');
}

// Fonctions communes
function renderSchedule(scheduleData) {
    const container = document.querySelector('#scheduleContainer');
    if (!container) return;

    const grouped = scheduleData.reduce((acc, item) => {
        acc[item.day] = acc[item.day] || [];
        acc[item.day].push(item);
        return acc;
    }, {});

    container.innerHTML = Object.entries(grouped).map(([day, courses]) => `
        <div class="col">
            <div class="card schedule-day">
                <div class="card-header bg-primary text-white">${day}</div>
                <div class="card-body">
                    ${courses.map(course => `
                        <div class="course-slot mb-3">
                            <div class="fw-bold">${course.name}</div>
                            <div>${course.start_time} - ${course.end_time}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

// Initialisation globale
window.addEventListener('DOMContentLoaded', async () => {
    // Réinitialiser les éléments UI
    ui = getUIElements();
    
    // Gestion des événements dynamique
    ui.loginForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        
        try {
            const response = await apiRequest('/login', 'POST', {
                username: formData.get('username'),
                password: formData.get('password')
            });
            
            auth.setToken(response.token);
            currentUser = await auth.getCurrentUser();
            await auth.updateAuthState();
            await loadUserData();
        } catch (error) {
            showError(error.message);
        }
    });

    ui.logoutBtn?.addEventListener('click', () => {
        auth.clearToken();
        currentUser = null;
        auth.updateAuthState();
    });

    // Initialiser l'application
    try {
        await auth.initialize();
        await loadUserData();
    } catch (error) {
        showError('Erreur initialisation application');
    }
});

// Gestion des rapports
window.generateStudentReport = async (studentId = currentUser?.id) => {
    if (!studentId) return;
    
    try {
        const pdfBlob = await apiRequest(`/report/student/${studentId}`);
        downloadPDF(pdfBlob, `bulletin_${studentId}.pdf`);
    } catch (error) {
        showError('Erreur génération bulletin');
    }
};

// Utilitaires
function downloadPDF(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
}

// Fonctions de chargement
function showLoadingSpinner() {
    const spinner = document.querySelector('#loadingSpinner') || createSpinner();
    spinner.classList.remove('hidden');
}

function hideLoadingSpinner() {
    const spinner = document.querySelector('#loadingSpinner');
    spinner?.classList?.add('hidden');
}

function createSpinner() {
    const spinner = document.createElement('div');
    spinner.id = 'loadingSpinner';
    spinner.className = 'spinner-border hidden';
    document.body.appendChild(spinner);
    return spinner;
}
