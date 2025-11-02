from flask import Flask, render_template, request, jsonify, send_file, session
import os
import uuid
import subprocess
import threading
import time
import shutil
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'deb-creator-secret-key-2024'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, 'projects')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Estado de compilación
compile_status = {}
compile_logs = {}

class DebProject:
    def __init__(self, project_id, name, description):
        self.id = project_id
        self.name = name
        self.description = description
        self.created_at = datetime.now().isoformat()
        self.files = {
            'control': self.get_default_control(),
            'main.m': self.get_default_main_m(),
            'makefile': self.get_default_makefile(),
            'info.plist': self.get_default_info_plist(),
            'postinst': '#!/bin/bash\necho "Post-installation script executed"',
            'prerm': '#!/bin/bash\necho "Pre-removal script executed"'
        }
        self.icon = None
        
    def get_default_control(self):
        return f"""Package: com.yourcompany.{self.name.lower()}
Name: {self.name}
Version: 1.0
Architecture: iphoneos-arm
Description: {self.description}
Maintainer: Your Name
Author: Your Name
Section: Utilities
Depends: firmware (>= 13.0)
"""

    def get_default_main_m(self):
        return f'''#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>

@interface {self.name.replace(" ", "")}ViewController : UIViewController
@end

@implementation {self.name.replace(" ", "")}ViewController

- (void)viewDidLoad {{
    [super viewDidLoad];
    [self setupUI];
}}

- (void)setupUI {{
    self.view.backgroundColor = [UIColor systemBackgroundColor];
    
    // Title Label
    UILabel *titleLabel = [[UILabel alloc] init];
    titleLabel.text = @"{self.name}";
    titleLabel.font = [UIFont boldSystemFontOfSize:24];
    titleLabel.textAlignment = NSTextAlignmentCenter;
    titleLabel.frame = CGRectMake(20, 100, self.view.frame.size.width - 40, 30);
    
    // Description Label
    UILabel *descLabel = [[UILabel alloc] init];
    descLabel.text = @"{self.description}";
    descLabel.font = [UIFont systemFontOfSize:16];
    descLabel.textColor = [UIColor secondaryLabelColor];
    descLabel.textAlignment = NSTextAlignmentCenter;
    descLabel.numberOfLines = 0;
    descLabel.frame = CGRectMake(20, 150, self.view.frame.size.width - 40, 60);
    
    [self.view addSubview:titleLabel];
    [self.view addSubview:descLabel];
}}

@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@end

@implementation AppDelegate

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {{
    self.window = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
    self.window.rootViewController = [[{self.name.replace(" ", "")}ViewController alloc] init];
    [self.window makeKeyAndVisible];
    return YES;
}}

@end

int main(int argc, char * argv[]) {{
    @autoreleasepool {{
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }}
}}
'''

    def get_default_makefile(self):
        return f'''ARCHS = arm64 arm64e
TARGET = iphone:clang:latest:13.0
INSTALL_TARGET_PROCESSES = SpringBoard

include $(THEOS)/makefiles/common.mk

APPLICATION_NAME = {self.name.replace(" ", "")}

{self.name.replace(" ", "")}_FILES = main.m
{self.name.replace(" ", "")}_FRAMEWORKS = UIKit Foundation
{self.name.replace(" ", "")}_CFLAGS = -fobjc-arc

include $(THEOS)/makefiles/application.mk

after-install::
	install.exec "killall -9 SpringBoard"
'''

    def get_default_info_plist(self):
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>{self.name.replace(" ", "")}</string>
    <key>CFBundleIdentifier</key>
    <string>com.yourcompany.{self.name.lower()}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>{self.name}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSRequiresIPhoneOS</key>
    <true/>
    <key>UIRequiredDeviceCapabilities</key>
    <array>
        <string>arm64</string>
    </array>
    <key>UISupportedInterfaceOrientations</key>
    <array>
        <string>UIInterfaceOrientationPortrait</string>
    </array>
</dict>
</plist>
'''

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at,
            'files': self.files,
            'icon': self.icon
        }

    @classmethod
    def from_dict(cls, data):
        project = cls(data['id'], data['name'], data['description'])
        project.created_at = data['created_at']
        project.files = data['files']
        project.icon = data.get('icon')
        return project

def save_project(project):
    project_path = os.path.join(PROJECTS_DIR, f"{project.id}.json")
    with open(project_path, 'w') as f:
        json.dump(project.to_dict(), f, indent=2)

def load_project(project_id):
    project_path = os.path.join(PROJECTS_DIR, f"{project_id}.json")
    if os.path.exists(project_path):
        with open(project_path, 'r') as f:
            data = json.load(f)
            return DebProject.from_dict(data)
    return None

def get_all_projects():
    projects = []
    for filename in os.listdir(PROJECTS_DIR):
        if filename.endswith('.json'):
            project_path = os.path.join(PROJECTS_DIR, filename)
            with open(project_path, 'r') as f:
                data = json.load(f)
                projects.append(DebProject.from_dict(data))
    return sorted(projects, key=lambda x: x.created_at, reverse=True)

def compile_deb_background(project_id, temp_dir):
    """Compila el proyecto .deb en segundo plano"""
    try:
        project = load_project(project_id)
        if not project:
            compile_status[project_id] = 'error'
            compile_logs[project_id] = 'Project not found'
            return

        compile_status[project_id] = 'compiling'
        compile_logs[project_id] = "🚀 Starting compilation...\n"
        
        # Crear estructura de directorios
        deb_dir = os.path.join(temp_dir, f"{project.name.replace(' ', '_')}")
        app_dir = os.path.join(deb_dir, "Applications", f"{project.name.replace(' ', '')}.app")
        debian_dir = os.path.join(deb_dir, "DEBIAN")
        
        os.makedirs(app_dir, exist_ok=True)
        os.makedirs(debian_dir, exist_ok=True)
        
        # Guardar archivos
        compile_logs[project_id] += "📁 Creating directory structure...\n"
        
        # Archivo control
        with open(os.path.join(debian_dir, "control"), "w") as f:
            f.write(project.files['control'])
        
        # Archivo main.m
        with open(os.path.join(app_dir, "main.m"), "w") as f:
            f.write(project.files['main.m'])
        
        # Archivo Info.plist
        with open(os.path.join(app_dir, "Info.plist"), "w") as f:
            f.write(project.files['info.plist'])
        
        # Scripts postinst/prerm
        if project.files.get('postinst'):
            with open(os.path.join(debian_dir, "postinst"), "w") as f:
                f.write(project.files['postinst'])
            os.chmod(os.path.join(debian_dir, "postinst"), 0o755)
        
        if project.files.get('prerm'):
            with open(os.path.join(debian_dir, "prerm"), "w") as f:
                f.write(project.files['prerm'])
            os.chmod(os.path.join(debian_dir, "prerm"), 0o755)
        
        compile_logs[project_id] += "✅ Project files created successfully\n"
        compile_logs[project_id] += "🔨 Building .deb package...\n"
        
        # Simular compilación (en un entorno real usarías dpkg-deb)
        time.sleep(2)
        
        # Crear archivo .deb simulado
        deb_filename = f"{project.name.replace(' ', '_')}_1.0_iphoneos-arm.deb"
        deb_path = os.path.join(temp_dir, deb_filename)
        
        with open(deb_path, 'w') as f:
            f.write(f"Simulated .deb package for {project.name}\n")
            f.write("In a real environment, this would be a proper .deb file\n")
        
        compile_logs[project_id] += f"✅ Compilation completed: {deb_filename}\n"
        compile_status[project_id] = 'completed'
        
    except Exception as e:
        compile_status[project_id] = 'error'
        compile_logs[project_id] += f"❌ Compilation failed: {str(e)}\n"

# Rutas de la aplicación
@app.route('/')
def index():
    projects = get_all_projects()
    return render_template_string(INDEX_HTML, projects=projects)

@app.route('/create', methods=['POST'])
def create_project():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    
    if not name:
        return jsonify({'success': False, 'error': 'Project name is required'})
    
    project_id = str(uuid.uuid4())
    project = DebProject(project_id, name, description)
    save_project(project)
    
    return jsonify({'success': True, 'project_id': project_id})

@app.route('/project/<project_id>')
def project_detail(project_id):
    project = load_project(project_id)
    if not project:
        return "Project not found", 404
    
    return render_template_string(PROJECT_HTML, project=project)

@app.route('/editor/<project_id>')
def project_editor(project_id):
    project = load_project(project_id)
    if not project:
        return "Project not found", 404
    
    return render_template_string(EDITOR_HTML, project=project)

@app.route('/api/project/<project_id>/file', methods=['GET', 'POST'])
def project_file(project_id):
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'})
    
    if request.method == 'GET':
        file_type = request.args.get('type')
        if file_type in project.files:
            return jsonify({'success': True, 'content': project.files[file_type]})
        return jsonify({'success': False, 'error': 'File type not found'})
    
    elif request.method == 'POST':
        data = request.get_json()
        file_type = data.get('type')
        content = data.get('content', '')
        
        if file_type in project.files:
            project.files[file_type] = content
            save_project(project)
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'Invalid file type'})

@app.route('/compile/<project_id>')
def compile_project(project_id):
    project = load_project(project_id)
    if not project:
        return "Project not found", 404
    
    return render_template_string(COMPILE_HTML, project=project)

@app.route('/api/compile/<project_id>/start', methods=['POST'])
def start_compile(project_id):
    if project_id in compile_status and compile_status[project_id] in ['compiling']:
        return jsonify({'success': False, 'error': 'Compilation already in progress'})
    
    # Crear directorio temporal para este proceso
    temp_dir = os.path.join(TEMP_DIR, project_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    # Iniciar compilación en segundo plano
    thread = threading.Thread(target=compile_deb_background, args=(project_id, temp_dir))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

@app.route('/api/compile/<project_id>/status')
def compile_status_api(project_id):
    status = compile_status.get(project_id, 'idle')
    logs = compile_logs.get(project_id, '')
    return jsonify({'status': status, 'logs': logs})

@app.route('/download/<project_id>')
def download_deb(project_id):
    project = load_project(project_id)
    if not project:
        return "Project not found", 404
    
    # En un entorno real, aquí enviarías el archivo .deb real
    deb_filename = f"{project.name.replace(' ', '_')}_1.0_iphoneos-arm.deb"
    deb_path = os.path.join(TEMP_DIR, project_id, deb_filename)
    
    if os.path.exists(deb_path):
        return send_file(deb_path, as_attachment=True, download_name=deb_filename)
    else:
        # Crear archivo simulado para descarga
        temp_deb = os.path.join(TEMP_DIR, f"temp_{deb_filename}")
        with open(temp_deb, 'w') as f:
            f.write(f"DEB Package: {project.name}\n")
            f.write(f"Version: 1.0\n")
            f.write(f"Architecture: iphoneos-arm\n")
            f.write(f"Description: {project.description}\n")
            f.write("\nThis is a simulated .deb file for demonstration.\n")
            f.write("In a production environment, this would be a real .deb package.\n")
        
        return send_file(temp_deb, as_attachment=True, download_name=deb_filename)

@app.route('/api/project/<project_id>/delete', methods=['POST'])
def delete_project(project_id):
    project_path = os.path.join(PROJECTS_DIR, f"{project_id}.json")
    if os.path.exists(project_path):
        os.remove(project_path)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Project not found'})

# Templates HTML embebidos
BASE_HTML = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}DebCreator Web{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .code-editor { font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace; }
        .log-output { background: #1a202c; color: #e2e8f0; }
    </style>
</head>
<body class="bg-gray-50">
    <!-- Navbar -->
    <nav class="gradient-bg text-white shadow-lg">
        <div class="container mx-auto px-4 py-3">
            <div class="flex justify-between items-center">
                <div class="flex items-center space-x-2">
                    <i class="fas fa-cube text-2xl"></i>
                    <h1 class="text-2xl font-bold">DebCreator Web</h1>
                </div>
                <div class="flex space-x-4">
                    <a href="/" class="hover:text-gray-200 transition duration-200">
                        <i class="fas fa-home mr-1"></i>Inicio
                    </a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="container mx-auto px-4 py-8">
        {% block content %}{% endblock %}
    </main>

    <!-- Footer -->
    <footer class="bg-gray-800 text-white py-6 mt-12">
        <div class="container mx-auto px-4 text-center">
            <p>&copy; 2024 DebCreator Web - Crea aplicaciones .deb desde tu navegador</p>
        </div>
    </footer>

    <script>
        // Funciones comunes JavaScript
        function showToast(message, type = 'success') {
            const toast = document.createElement('div');
            toast.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg text-white ${
                type === 'success' ? 'bg-green-500' : 'bg-red-500'
            } z-50`;
            toast.textContent = message;
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.remove();
            }, 3000);
        }
        
        function confirmAction(message) {
            return confirm(message);
        }
    </script>
    
    {% block scripts %}{% endblock %}
</body>
</html>
'''

INDEX_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block title %}Inicio - DebCreator Web{% endblock %}
{% block content %}
<div class="max-w-6xl mx-auto">
    <!-- Header -->
    <div class="text-center mb-12">
        <h2 class="text-4xl font-bold text-gray-800 mb-4">Crea Aplicaciones .deb para iOS</h2>
        <p class="text-xl text-gray-600">Diseña, compila y descarga paquetes .deb directamente desde tu navegador</p>
    </div>

    <!-- Create Project Card -->
    <div class="bg-white rounded-xl shadow-lg p-8 mb-8 border border-gray-200">
        <h3 class="text-2xl font-bold text-gray-800 mb-6 flex items-center">
            <i class="fas fa-plus-circle text-blue-500 mr-3"></i>
            Nuevo Proyecto
        </h3>
        
        <form id="createProjectForm" class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Nombre del Proyecto</label>
                <input type="text" name="name" required 
                       class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                       placeholder="Mi Aplicación Increíble">
            </div>
            
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Descripción</label>
                <textarea name="description" rows="3"
                          class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          placeholder="Describe tu aplicación..."></textarea>
            </div>
            
            <button type="submit" 
                    class="w-full bg-blue-500 hover:bg-blue-600 text-white font-bold py-3 px-6 rounded-lg transition duration-200 flex items-center justify-center">
                <i class="fas fa-rocket mr-2"></i>
                Crear Proyecto
            </button>
        </form>
    </div>

    <!-- Projects List -->
    <div class="bg-white rounded-xl shadow-lg p-8 border border-gray-200">
        <h3 class="text-2xl font-bold text-gray-800 mb-6 flex items-center">
            <i class="fas fa-folder-open text-green-500 mr-3"></i>
            Mis Proyectos
        </h3>
        
        {% if projects %}
        <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {% for project in projects %}
            <div class="border border-gray-200 rounded-lg p-6 hover:shadow-md transition duration-200">
                <div class="flex justify-between items-start mb-3">
                    <h4 class="text-lg font-semibold text-gray-800">{{ project.name }}</h4>
                    <span class="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">{{ project.id[:8] }}...</span>
                </div>
                
                <p class="text-gray-600 text-sm mb-4">{{ project.description }}</p>
                
                <div class="text-xs text-gray-500 mb-4">
                    <i class="fas fa-calendar mr-1"></i>
                    {{ project.created_at[:10] }}
                </div>
                
                <div class="flex space-x-2">
                    <a href="/project/{{ project.id }}" 
                       class="flex-1 bg-blue-500 hover:bg-blue-600 text-white text-center py-2 px-3 rounded text-sm transition duration-200">
                        <i class="fas fa-edit mr-1"></i>Editar
                    </a>
                    <a href="/compile/{{ project.id }}" 
                       class="flex-1 bg-green-500 hover:bg-green-600 text-white text-center py-2 px-3 rounded text-sm transition duration-200">
                        <i class="fas fa-hammer mr-1"></i>Compilar
                    </a>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="text-center py-12 text-gray-500">
            <i class="fas fa-inbox text-4xl mb-4"></i>
            <p>No hay proyectos creados todavía</p>
            <p class="text-sm">¡Comienza creando tu primer proyecto arriba!</p>
        </div>
        {% endif %}
    </div>
</div>

<script>
document.getElementById('createProjectForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const response = await fetch('/create', {
        method: 'POST',
        body: formData
    });
    
    const result = await response.json();
    
    if (result.success) {
        showToast('Proyecto creado exitosamente!', 'success');
        setTimeout(() => {
            window.location.href = `/project/${result.project_id}`;
        }, 1000);
    } else {
        showToast(result.error, 'error');
    }
});
</script>
{% endblock %}
''')

PROJECT_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block title %}{{ project.name }} - DebCreator Web{% endblock %}
{% block content %}
<div class="max-w-6xl mx-auto">
    <!-- Project Header -->
    <div class="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-200">
        <div class="flex justify-between items-start">
            <div>
                <h2 class="text-3xl font-bold text-gray-800">{{ project.name }}</h2>
                <p class="text-gray-600 mt-2">{{ project.description }}</p>
                <div class="flex items-center mt-3 text-sm text-gray-500">
                    <i class="fas fa-calendar mr-1"></i>
                    Creado: {{ project.created_at[:10] }}
                    <span class="mx-2">•</span>
                    <i class="fas fa-fingerprint mr-1"></i>
                    ID: {{ project.id[:8] }}...
                </div>
            </div>
            <div class="flex space-x-3">
                <a href="/editor/{{ project.id }}" 
                   class="bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold transition duration-200 flex items-center">
                    <i class="fas fa-code mr-2"></i>Editor de Código
                </a>
                <a href="/compile/{{ project.id }}" 
                   class="bg-green-500 hover:bg-green-600 text-white px-6 py-3 rounded-lg font-semibold transition duration-200 flex items-center">
                    <i class="fas fa-hammer mr-2"></i>Compilar
                </a>
                <a href="/" 
                   class="bg-gray-500 hover:bg-gray-600 text-white px-6 py-3 rounded-lg font-semibold transition duration-200 flex items-center">
                    <i class="fas fa-arrow-left mr-2"></i>Volver
                </a>
            </div>
        </div>
    </div>

    <!-- File Preview -->
    <div class="grid gap-6 lg:grid-cols-2">
        <!-- Control File -->
        <div class="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
            <h3 class="text-xl font-bold text-gray-800 mb-4 flex items-center">
                <i class="fas fa-cog text-purple-500 mr-2"></i>
                Archivo Control
            </h3>
            <pre class="bg-gray-800 text-green-400 p-4 rounded-lg overflow-x-auto text-sm"><code>{{ project.files.control }}</code></pre>
        </div>

        <!-- Main.m Preview -->
        <div class="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
            <h3 class="text-xl font-bold text-gray-800 mb-4 flex items-center">
                <i class="fas fa-file-code text-blue-500 mr-2"></i>
                Código Principal (main.m)
            </h3>
            <pre class="bg-gray-800 text-yellow-400 p-4 rounded-lg overflow-x-auto text-sm max-h-96 overflow-y-auto"><code>{{ project.files.main.m }}</code></pre>
        </div>
    </div>

    <!-- Additional Files -->
    <div class="mt-6 bg-white rounded-xl shadow-lg p-6 border border-gray-200">
        <h3 class="text-xl font-bold text-gray-800 mb-4">Archivos del Proyecto</h3>
        <div class="grid gap-4 md:grid-cols-3">
            <div class="border border-gray-200 rounded-lg p-4">
                <h4 class="font-semibold text-gray-800 mb-2 flex items-center">
                    <i class="fas fa-wrench text-orange-500 mr-2"></i>Makefile
                </h4>
                <pre class="text-xs bg-gray-100 p-2 rounded overflow-x-auto"><code>{{ project.files.makefile[:100] }}...</code></pre>
            </div>
            <div class="border border-gray-200 rounded-lg p-4">
                <h4 class="font-semibold text-gray-800 mb-2 flex items-center">
                    <i class="fas fa-info-circle text-blue-500 mr-2"></i>Info.plist
                </h4>
                <pre class="text-xs bg-gray-100 p-2 rounded overflow-x-auto"><code>{{ project.files.info.plist[:100] }}...</code></pre>
            </div>
            <div class="border border-gray-200 rounded-lg p-4">
                <h4 class="font-semibold text-gray-800 mb-2 flex items-center">
                    <i class="fas fa-terminal text-green-500 mr-2"></i>Scripts
                </h4>
                <p class="text-sm text-gray-600">postinst, prerm disponibles</p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
''')

EDITOR_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block title %}Editor - {{ project.name }}{% endblock %}
{% block content %}
<div class="max-w-7xl mx-auto">
    <!-- Editor Header -->
    <div class="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-200">
        <div class="flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold text-gray-800 flex items-center">
                    <i class="fas fa-code mr-3 text-blue-500"></i>
                    Editor: {{ project.name }}
                </h2>
                <p class="text-gray-600 mt-1">Edita los archivos de tu proyecto .deb</p>
            </div>
            <div class="flex space-x-3">
                <button onclick="saveFile()" 
                        class="bg-green-500 hover:bg-green-600 text-white px-6 py-3 rounded-lg font-semibold transition duration-200 flex items-center">
                    <i class="fas fa-save mr-2"></i>Guardar
                </button>
                <a href="/project/{{ project.id }}" 
                   class="bg-gray-500 hover:bg-gray-600 text-white px-6 py-3 rounded-lg font-semibold transition duration-200 flex items-center">
                    <i class="fas fa-arrow-left mr-2"></i>Volver
                </a>
            </div>
        </div>
    </div>

    <div class="grid gap-6 lg:grid-cols-4">
        <!-- File Navigator -->
        <div class="lg:col-span-1">
            <div class="bg-white rounded-xl shadow-lg p-6 border border-gray-200 sticky top-6">
                <h3 class="text-lg font-bold text-gray-800 mb-4">Archivos</h3>
                <div class="space-y-2">
                    {% for file_type in ['control', 'main.m', 'makefile', 'info.plist', 'postinst', 'prerm'] %}
                    <button onclick="loadFile('{{ file_type }}')" 
                            class="w-full text-left px-4 py-3 rounded-lg border border-gray-200 hover:bg-blue-50 hover:border-blue-300 transition duration-200 file-btn" 
                            id="btn-{{ file_type }}">
                        <div class="flex items-center">
                            <i class="fas fa-file-code text-blue-500 mr-3"></i>
                            <div>
                                <div class="font-medium text-gray-800">{{ file_type }}</div>
                                <div class="text-xs text-gray-500">
                                    {% if file_type == 'control' %}Configuración DEB
                                    {% elif file_type == 'main.m' %}Código Objective-C
                                    {% elif file_type == 'makefile' %}Script de compilación
                                    {% elif file_type == 'info.plist' %}Info de aplicación
                                    {% elif file_type == 'postinst' %}Script post-instalación
                                    {% elif file_type == 'prerm' %}Script pre-remoción
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                    </button>
                    {% endfor %}
                </div>
                
                <div class="mt-6 pt-6 border-t border-gray-200">
                    <div class="text-xs text-gray-500 mb-2">Estado del archivo:</div>
                    <div id="fileStatus" class="text-sm text-green-600">
                        <i class="fas fa-check-circle mr-1"></i>Listo
                    </div>
                </div>
            </div>
        </div>

        <!-- Code Editor -->
        <div class="lg:col-span-3">
            <div class="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
                <div class="bg-gray-800 text-white px-6 py-4 flex justify-between items-center">
                    <div class="flex items-center">
                        <i class="fas fa-file-code mr-3 text-yellow-400"></i>
                        <span id="currentFile" class="font-mono font-bold">Selecciona un archivo</span>
                    </div>
                    <div class="flex items-center space-x-4">
                        <span id="lineCount" class="text-sm text-gray-300">0 líneas</span>
                        <div class="flex space-x-2">
                            <button onclick="formatCode()" class="text-xs bg-gray-700 hover:bg-gray-600 px-3 py-1 rounded transition duration-200">
                                <i class="fas fa-indent mr-1"></i>Formatear
                            </button>
                        </div>
                    </div>
                </div>
                
                <div class="p-1 bg-gray-800">
                    <textarea id="codeEditor" 
                              class="w-full h-96 code-editor bg-gray-900 text-green-400 p-6 rounded-lg focus:outline-none resize-none"
                              spellcheck="false"
                              placeholder="Selecciona un archivo para editar..."></textarea>
                </div>
                
                <div class="bg-gray-100 px-6 py-4 border-t border-gray-200">
                    <div class="flex justify-between items-center">
                        <div id="editorStatus" class="text-sm text-gray-600">
                            <i class="fas fa-info-circle mr-1"></i>Presiona Ctrl+S para guardar
                        </div>
                        <div class="flex space-x-3">
                            <button onclick="loadFile(currentFileType)" 
                                    class="text-gray-600 hover:text-gray-800 transition duration-200">
                                <i class="fas fa-sync-alt mr-1"></i>Recargar
                            </button>
                            <button onclick="saveFile()" 
                                    class="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold transition duration-200 flex items-center">
                                <i class="fas fa-save mr-2"></i>Guardar Cambios
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
let currentFileType = '';
let originalContent = '';

// Cargar archivo
async function loadFile(fileType) {
    try {
        const response = await fetch(`/api/project/{{ project.id }}/file?type=${fileType}`);
        const result = await response.json();
        
        if (result.success) {
            currentFileType = fileType;
            originalContent = result.content;
            
            document.getElementById('codeEditor').value = result.content;
            document.getElementById('currentFile').textContent = fileType;
            document.getElementById('lineCount').textContent = `${result.content.split('\\n').length} líneas`;
            
            // Actualizar botones activos
            document.querySelectorAll('.file-btn').forEach(btn => {
                btn.classList.remove('bg-blue-100', 'border-blue-400');
            });
            document.getElementById(`btn-${fileType}`).classList.add('bg-blue-100', 'border-blue-400');
            
            updateFileStatus('loaded');
        }
    } catch (error) {
        showToast('Error cargando archivo', 'error');
    }
}

// Guardar archivo
async function saveFile() {
    if (!currentFileType) {
        showToast('Selecciona un archivo primero', 'error');
        return;
    }
    
    const content = document.getElementById('codeEditor').value;
    
    try {
        const response = await fetch(`/api/project/{{ project.id }}/file`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: currentFileType,
                content: content
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            originalContent = content;
            updateFileStatus('saved');
            showToast('Archivo guardado exitosamente', 'success');
        } else {
            showToast('Error guardando archivo', 'error');
        }
    } catch (error) {
        showToast('Error de conexión', 'error');
    }
}

// Formatear código
function formatCode() {
    const editor = document.getElementById('codeEditor');
    const content = editor.value;
    
    // Formateo básico (en un entorno real usarías una librería de formateo)
    let formatted = content
        .replace(/\\n\\n\\n+/g, '\\n\\n')  // Remover múltiples líneas vacías
        .replace(/\\t/g, '    ');          // Reemplazar tabs con espacios
    
    editor.value = formatted;
    updateFileStatus('modified');
    showToast('Código formateado', 'success');
}

// Estado del archivo
function updateFileStatus(status) {
    const statusElement = document.getElementById('fileStatus');
    const editorElement = document.getElementById('editorStatus');
    
    switch(status) {
        case 'loaded':
            statusElement.innerHTML = '<i class="fas fa-check-circle mr-1"></i>Cargado';
            statusElement.className = 'text-sm text-green-600';
            editorElement.innerHTML = '<i class="fas fa-info-circle mr-1"></i>Archivo cargado - Presiona Ctrl+S para guardar';
            break;
        case 'modified':
            statusElement.innerHTML = '<i class="fas fa-edit mr-1"></i>Modificado';
            statusElement.className = 'text-sm text-yellow-600';
            editorElement.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i>Cambios sin guardar - Presiona Ctrl+S para guardar';
            break;
        case 'saved':
            statusElement.innerHTML = '<i class="fas fa-check-circle mr-1"></i>Guardado';
            statusElement.className = 'text-sm text-green-600';
            editorElement.innerHTML = '<i class="fas fa-check-circle mr-1"></i>Todos los cambios guardados';
            break;
    }
}

// Atajos de teclado
document.getElementById('codeEditor').addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        saveFile();
    }
});

// Detectar cambios
document.getElementById('codeEditor').addEventListener('input', () => {
    const currentContent = document.getElementById('codeEditor').value;
    if (currentContent !== originalContent) {
        updateFileStatus('modified');
    }
});

// Cargar el primer archivo por defecto
document.addEventListener('DOMContentLoaded', () => {
    loadFile('control');
});
</script>
{% endblock %}
''')

COMPILE_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block title %}Compilar - {{ project.name }}{% endblock %}
{% block content %}
<div class="max-w-4xl mx-auto">
    <!-- Compile Header -->
    <div class="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-200">
        <div class="flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold text-gray-800 flex items-center">
                    <i class="fas fa-hammer mr-3 text-green-500"></i>
                    Compilar: {{ project.name }}
                </h2>
                <p class="text-gray-600 mt-1">Compila tu proyecto en un paquete .deb listo para instalar</p>
            </div>
            <div class="flex space-x-3">
                <a href="/project/{{ project.id }}" 
                   class="bg-gray-500 hover:bg-gray-600 text-white px-6 py-3 rounded-lg font-semibold transition duration-200 flex items-center">
                    <i class="fas fa-arrow-left mr-2"></i>Volver
                </a>
            </div>
        </div>
    </div>

    <!-- Compilation Panel -->
    <div class="bg-white rounded-xl shadow-lg p-6 border border-gray-200 mb-6">
        <div class="text-center mb-8">
            <div class="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <i class="fas fa-cube text-green-500 text-3xl"></i>
            </div>
            <h3 class="text-xl font-bold text-gray-800 mb-2">Compilar Proyecto</h3>
            <p class="text-gray-600">Genera el archivo .deb para instalar en dispositivos jailbreak</p>
        </div>

        <!-- Compilation Controls -->
        <div class="flex justify-center space-x-4 mb-8">
            <button id="startCompile" 
                    class="bg-green-500 hover:bg-green-600 text-white px-8 py-4 rounded-lg font-bold text-lg transition duration-200 flex items-center">
                <i class="fas fa-play-circle mr-3"></i>
                Iniciar Compilación
            </button>
            
            <button id="downloadBtn" 
                    class="bg-blue-500 hover:bg-blue-600 text-white px-8 py-4 rounded-lg font-bold text-lg transition duration-200 flex items-center hidden">
                <i class="fas fa-download mr-3"></i>
                Descargar .deb
            </button>
        </div>

        <!-- Progress -->
        <div id="progressSection" class="hidden">
            <div class="mb-4">
                <div class="flex justify-between text-sm text-gray-600 mb-2">
                    <span id="progressText">Preparando compilación...</span>
                    <span id="progressPercent">0%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3">
                    <div id="progressBar" class="bg-green-500 h-3 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Compilation Logs -->
    <div class="bg-white rounded-xl shadow-lg border border-gray-200">
        <div class="bg-gray-800 text-white px-6 py-4 rounded-t-xl">
            <h3 class="text-lg font-bold flex items-center">
                <i class="fas fa-terminal mr-3 text-yellow-400"></i>
                Logs de Compilación
            </h3>
        </div>
        
        <div class="p-1 bg-gray-800">
            <pre id="compileLogs" class="log-output p-6 rounded-b-xl h-96 overflow-y-auto text-sm font-mono whitespace-pre-wrap"></pre>
        </div>
        
        <div class="bg-gray-100 px-6 py-4 border-t border-gray-200 rounded-b-xl">
            <div class="flex justify-between items-center">
                <div id="compileStatus" class="text-sm text-gray-600">
                    <i class="fas fa-info-circle mr-1"></i>Listo para compilar
                </div>
                <div class="flex space-x-3">
                    <button onclick="clearLogs()" class="text-gray-600 hover:text-gray-800 transition duration-200">
                        <i class="fas fa-broom mr-1"></i>Limpiar
                    </button>
                    <button onclick="scrollToBottom()" class="text-gray-600 hover:text-gray-800 transition duration-200">
                        <i class="fas fa-arrow-down mr-1"></i>Ir al final
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
let compileInterval;

// Iniciar compilación
document.getElementById('startCompile').addEventListener('click', async () => {
    const startBtn = document.getElementById('startCompile');
    const progressSection = document.getElementById('progressSection');
    const downloadBtn = document.getElementById('downloadBtn');
    
    startBtn.disabled = true;
    startBtn.innerHTML = '<i class="fas fa-sync-alt fa-spin mr-3"></i>Compilando...';
    progressSection.classList.remove('hidden');
    downloadBtn.classList.add('hidden');
    
    // Iniciar compilación
    try {
        const response = await fetch(`/api/compile/{{ project.id }}/start`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Iniciar polling de estado
            compileInterval = setInterval(updateCompileStatus, 1000);
            updateCompileStatus();
        } else {
            showToast(result.error, 'error');
            resetCompileButton();
        }
    } catch (error) {
        showToast('Error iniciando compilación', 'error');
        resetCompileButton();
    }
});

// Actualizar estado de compilación
async function updateCompileStatus() {
    try {
        const response = await fetch(`/api/compile/{{ project.id }}/status`);
        const result = await response.json();
        
        const logsElement = document.getElementById('compileLogs');
        const statusElement = document.getElementById('compileStatus');
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        const progressPercent = document.getElementById('progressPercent');
        
        // Actualizar logs
        logsElement.textContent = result.logs;
        scrollToBottom();
        
        // Actualizar progreso basado en estado
        switch(result.status) {
            case 'compiling':
                progressBar.style.width = '50%';
                progressPercent.textContent = '50%';
                progressText.textContent = 'Compilando proyecto...';
                statusElement.innerHTML = '<i class="fas fa-sync-alt fa-spin mr-1"></i>Compilando...';
                break;
                
            case 'completed':
                progressBar.style.width = '100%';
                progressPercent.textContent = '100%';
                progressText.textContent = 'Compilación completada!';
                statusElement.innerHTML = '<i class="fas fa-check-circle text-green-500 mr-1"></i>Compilación exitosa';
                
                // Mostrar botón de descarga
                document.getElementById('downloadBtn').classList.remove('hidden');
                document.getElementById('startCompile').classList.add('hidden');
                
                clearInterval(compileInterval);
                showToast('Compilación completada exitosamente!', 'success');
                break;
                
            case 'error':
                progressBar.style.width = '100%';
                progressBar.className = 'bg-red-500 h-3 rounded-full';
                progressPercent.textContent = 'Error';
                progressText.textContent = 'Error en compilación';
                statusElement.innerHTML = '<i class="fas fa-times-circle text-red-500 mr-1"></i>Error en compilación';
                
                clearInterval(compileInterval);
                resetCompileButton();
                showToast('Error durante la compilación', 'error');
                break;
        }
        
    } catch (error) {
        console.error('Error checking compile status:', error);
    }
}

// Descargar .deb
document.getElementById('downloadBtn').addEventListener('click', () => {
    window.location.href = `/download/{{ project.id }}`;
});

// Utilidades
function resetCompileButton() {
    const startBtn = document.getElementById('startCompile');
    startBtn.disabled = false;
    startBtn.innerHTML = '<i class="fas fa-play-circle mr-3"></i>Iniciar Compilación';
}

function clearLogs() {
    document.getElementById('compileLogs').textContent = '';
}

function scrollToBottom() {
    const logsElement = document.getElementById('compileLogs');
    logsElement.scrollTop = logsElement.scrollHeight;
}

// Auto-scroll cuando hay nuevos logs
const observer = new MutationObserver(scrollToBottom);
observer.observe(document.getElementById('compileLogs'), {
    childList: true,
    subtree: true
});
</script>
{% endblock %}
''')

if __name__ == '__main__':
    # Crear proyectos de ejemplo si no existen
    if not get_all_projects():
        sample_project = DebProject(str(uuid.uuid4()), "Mi Primera App", "Una aplicación de ejemplo creada con DebCreator Web")
        save_project(sample_project)
    
    print("🚀 DebCreator Web iniciando...")
    print("📁 Directorio de proyectos:", PROJECTS_DIR)
    print("🌐 Servidor ejecutándose en: http://localhost:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
