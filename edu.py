# main.py
# noinspection PyArgumentList
# Небольшая админка для управления учебными данными через Tkinter и MySQL.

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import mysql.connector
from datetime import datetime
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ---------- DB connection ----------
# Конфигурация подключения к базе данных MySQL — БЕЗ пароля в коде
DB_CONFIG = {
    'host': os.getenv("DB_HOST", "127.0.0.1"),
    'user': os.getenv("DB_USER", "root"),
    'password': os.getenv("DB_PASSWORD", ""),
    'database': os.getenv("DB_NAME", "education_manager"),
    'charset': 'utf8mb4'
}

def get_connection():
    """Создать и вернуть новое соединение с БД."""
    return mysql.connector.connect(**DB_CONFIG)

# ---------- Helper utilities ----------
def fetch_all(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def execute(query, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    last = cur.lastrowid
    cur.close()
    conn.close()
    return last


# ---------- Ensure required tables exist ----------
def create_tables_if_not_exist():
    """Создать все необходимые таблицы, если их нет."""
    conn = get_connection()
    cur = conn.cursor()

    # module table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS module (
        id INT PRIMARY KEY AUTO_INCREMENT,
        code VARCHAR(50),
        title VARCHAR(255),
        total_hours INT
    ) ENGINE=InnoDB;
    """)

    # ro_sections
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ro_sections (
        id INT PRIMARY KEY AUTO_INCREMENT,
        module_id INT,
        code VARCHAR(100),
        title VARCHAR(255),
        hours INT DEFAULT 0,
        FOREIGN KEY (module_id) REFERENCES module(id)
            ON DELETE RESTRICT ON UPDATE CASCADE
    ) ENGINE=InnoDB;
    """)

    # lessons
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lessons (
        id INT PRIMARY KEY AUTO_INCREMENT,
        ro_id INT,
        number INT,
        criteria TEXT,
        total_hours INT,
        type VARCHAR(100),
        FOREIGN KEY (ro_id) REFERENCES ro_sections(id)
            ON DELETE RESTRICT ON UPDATE CASCADE
    ) ENGINE=InnoDB;
    """)

    # teachers
    cur.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INT PRIMARY KEY AUTO_INCREMENT,
        full_name VARCHAR(255),
        position VARCHAR(255)
    ) ENGINE=InnoDB;
    """)

    # students
    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INT PRIMARY KEY AUTO_INCREMENT,
        full_name VARCHAR(255),
        birthdate DATE,
        class VARCHAR(50)
    ) ENGINE=InnoDB;
    """)

    # class_plans
    cur.execute("""
    CREATE TABLE IF NOT EXISTS class_plans (
        id INT PRIMARY KEY AUTO_INCREMENT,
        teacher_id INT,
        class VARCHAR(50),
        year INT,
        file_path TEXT,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            ON DELETE SET NULL ON UPDATE CASCADE
    ) ENGINE=InnoDB;
    """)

    # social_passport (добавлена колонка many_children)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS social_passport (
        id INT PRIMARY KEY AUTO_INCREMENT,
        class VARCHAR(50),
        year INT,
        total_students INT,
        full_families INT,
        low_income INT,
        disabilities INT,
        orphaned INT,
        many_children INT DEFAULT 0
    ) ENGINE=InnoDB;
    """)

    # grade_reports (используем s1, s2 вместо q1..q4)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS grade_reports (
        id INT PRIMARY KEY AUTO_INCREMENT,
        student_id INT,
        subject VARCHAR(255),
        s1 INT,
        s2 INT,
        final_grade INT,
        FOREIGN KEY (student_id) REFERENCES students(id)
            ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB;
    """)

    # exam_protocols
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_protocols (
        id INT PRIMARY KEY AUTO_INCREMENT,
        teacher_id INT,
        subject VARCHAR(255),
        class VARCHAR(50),
        date DATE,
        file_path TEXT,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            ON DELETE SET NULL ON UPDATE CASCADE
    ) ENGINE=InnoDB;
    """)

    conn.commit()
    cur.close()
    conn.close()

    # Ensure at least one module exists (module_id=1) to avoid FK problems
    ensure_module_exists()

    # Ensure semester columns exist and migrate if needed
    ensure_semesters_and_migrate_if_needed()

def ensure_module_exists():
    """Гарантировать наличие хотя бы одного модуля в таблице module."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM module LIMIT 1")
    if not cur.fetchone():
        # Вставляем автосозданный модуль, чтобы FK не ломались
        cur.execute("INSERT INTO module (code, title, total_hours) VALUES ('ПМ6', 'Автосозданный модуль', 0)")
        conn.commit()
    cur.close()
    conn.close()

# ---------- Migration and column helpers ----------
def ensure_semesters_and_migrate_if_needed():
    """Добавить колонки s1/s2 и перенести данные из q1..q4 при необходимости."""
    conn = get_connection()
    cur = conn.cursor()

    # добавить s1/s2 если нет
    cur.execute("SHOW COLUMNS FROM grade_reports LIKE 's1'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE grade_reports ADD COLUMN s1 INT DEFAULT NULL")
    cur.execute("SHOW COLUMNS FROM grade_reports LIKE 's2'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE grade_reports ADD COLUMN s2 INT DEFAULT NULL")

    # проверить, существуют ли колонки q1..q4
    cur.execute("SHOW COLUMNS FROM grade_reports LIKE 'q1'")
    q1_exists = bool(cur.fetchone())
    cur.execute("SHOW COLUMNS FROM grade_reports LIKE 'q2'")
    q2_exists = bool(cur.fetchone())
    cur.execute("SHOW COLUMNS FROM grade_reports LIKE 'q3'")
    q3_exists = bool(cur.fetchone())
    cur.execute("SHOW COLUMNS FROM grade_reports LIKE 'q4'")
    q4_exists = bool(cur.fetchone())

    # если четверти существуют — проверить, есть ли в них данные
    if q1_exists or q2_exists or q3_exists or q4_exists:
        # посчитать ненулевые значения в q1..q4
        cur.execute("""
            SELECT
              SUM(q1 IS NOT NULL) AS q1_not_null,
              SUM(q2 IS NOT NULL) AS q2_not_null,
              SUM(q3 IS NOT NULL) AS q3_not_null,
              SUM(q4 IS NOT NULL) AS q4_not_null
            FROM grade_reports
        """)
        counts = cur.fetchone() or (0,0,0,0)
        total_not_null = sum(counts)

        if total_not_null > 0:
            # переносим данные из q1..q4 в s1/s2 (логика усреднения)
            cur.execute("""
                UPDATE grade_reports
                SET s1 = CASE WHEN q1 IS NULL AND q2 IS NULL THEN NULL
                              WHEN q1 IS NULL THEN q2
                              WHEN q2 IS NULL THEN q1
                              ELSE ROUND((q1 + q2) / 2) END,
                    s2 = CASE WHEN q3 IS NULL AND q4 IS NULL THEN NULL
                              WHEN q3 IS NULL THEN q4
                              WHEN q4 IS NULL THEN q3
                              ELSE ROUND((q3 + q4) / 2) END
            """)
            # пересчитать final_grade по семестрам
            cur.execute("""
                UPDATE grade_reports
                SET final_grade = CASE WHEN s1 IS NULL AND s2 IS NULL THEN NULL
                                       WHEN s1 IS NULL THEN s2
                                       WHEN s2 IS NULL THEN s1
                                       ELSE ROUND((s1 + s2) / 2) END
            """)
            conn.commit()

        else:
            # если данных в q1..q4 нет — просто пересчитать final_grade по s1/s2
            cur.execute("""
                UPDATE grade_reports
                SET final_grade = CASE WHEN s1 IS NULL AND s2 IS NULL THEN NULL
                                       WHEN s1 IS NULL THEN s2
                                       WHEN s2 IS NULL THEN s1
                                       ELSE ROUND((s1 + s2) / 2) END
            """)
            conn.commit()

    cur.close()
    conn.close()

# ---------- GUI app ----------
class AdminApp:
    """Главное приложение с вкладками для управления данными."""
    def __init__(self, master):
        self.master = master
        master.title("ASPC админка")
        master.geometry("1100x620")

        # create tabs
        self.tab_control = ttk.Notebook(master)
        self.tab_control.pack(fill=tk.BOTH, expand=True)

        # prepare tabs
        self.tabs = {}
        self.create_lessons_tab()
        self.create_teachers_tab()
        self.create_students_tab()
        self.create_class_plans_tab()
        self.create_social_passport_tab()
        self.create_grade_reports_tab()
        self.create_exam_protocols_tab()

    # ---------------- lessons tab ----------------
    def create_lessons_tab(self):
        """Создать вкладку Уроки / КТП."""
        tab = ttk.Frame(self.tab_control)
        self.tab_control.add(tab, text="Уроки / КТП")
        self.tabs['lessons'] = tab

        cols = ("id", "section", "num", "crit", "hours", "type")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        for c, txt in zip(cols, ["ID", "Раздел", "№", "Критерии", "Часы", "Тип"]):
            tree.heading(c, text=txt)
            tree.column(c, width=120 if c!='crit' else 350)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.lessons_tree = tree

        # кнопки управления
        f = tk.Frame(tab)
        f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Добавить", command=self.lessons_add, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Редактировать", command=self.lessons_edit, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Удалить", command=self.lessons_delete, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Обновить", command=self.lessons_load, width=14).pack(side=tk.LEFT, padx=5)
        self.lessons_load()

    def lessons_load(self):
        """Загрузить список уроков в дерево."""
        for i in self.lessons_tree.get_children(): self.lessons_tree.delete(i)
        rows = fetch_all("""
            SELECT lessons.id, ro_sections.title, lessons.number, lessons.criteria, lessons.total_hours, lessons.type
            FROM lessons
            LEFT JOIN ro_sections ON ro_sections.id = lessons.ro_id
            ORDER BY lessons.id DESC
        """)
        for r in rows:
            self.lessons_tree.insert("", tk.END, values=r)

    def get_or_create_section_simple(self, title):
        """Найти раздел по названию или создать новый и вернуть id."""
        row = fetch_all("SELECT id FROM ro_sections WHERE title=%s", (title,))
        if row:
            return row[0][0]
        last = execute("INSERT INTO ro_sections (module_id, code, title, hours) VALUES (1, %s, %s, 0)", (title[:10], title))
        return last

    def lessons_add(self):
        """Окно добавления урока."""
        win = tk.Toplevel(self.master)
        win.title("Добавить урок")
        win.geometry("620x240")
        tk.Label(win, text="Раздел / предмет:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        sections = ["РО 6.1", "РО 6.2", "РО 6.3"] + [r[0] for r in fetch_all("SELECT title FROM ro_sections ORDER BY title")]
        combo_section = ttk.Combobox(win, values=sections)
        combo_section.grid(row=0, column=1, sticky="we", padx=6)
        combo_section.set("РО 6.1")

        tk.Label(win, text="Номер:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        ent_num = tk.Entry(win); ent_num.grid(row=1, column=1, sticky="we", padx=6)

        tk.Label(win, text="Тема / критерии:").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        ent_crit = tk.Entry(win); ent_crit.grid(row=2, column=1, sticky="we", padx=6)

        tk.Label(win, text="Часы:").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        ent_hours = tk.Entry(win); ent_hours.grid(row=3, column=1, sticky="we", padx=6)

        tk.Label(win, text="Тип:").grid(row=4, column=0, sticky="e", padx=6, pady=6)
        combo_type = ttk.Combobox(win, values=["комбинированный", "практический"])
        combo_type.grid(row=4, column=1, sticky="we", padx=6)
        combo_type.set("комбинированный")

        def do_save():
            """Сохранить новый урок в БД."""
            section = combo_section.get().strip()
            if not section:
                messagebox.showerror("Ошибка", "Раздел обязателен")
                return
            try:
                number = int(ent_num.get())
                hours = int(ent_hours.get())
            except:
                messagebox.showerror("Ошибка", "Номер и Часы должны быть числами")
                return
            title = ent_crit.get().strip()
            if not title:
                messagebox.showerror("Ошибка", "Введите тему/критерии")
                return
            ro_id = self.get_or_create_section_simple(section)
            execute("INSERT INTO lessons (ro_id, number, criteria, total_hours, type) VALUES (%s,%s,%s,%s,%s)",
                    (ro_id, number, title, hours, combo_type.get()))
            win.destroy()
            self.lessons_load()

        tk.Button(win, text="Сохранить", command=do_save).grid(row=5, column=0, columnspan=2, pady=10)

    def lessons_edit(self):
        """Окно редактирования выбранного урока."""
        sel = self.lessons_tree.selection()
        if not sel:
            messagebox.showwarning("Ошибка", "Выберите запись")
            return
        item = self.lessons_tree.item(sel[0])['values']
        lesson_id = item[0]
        win = tk.Toplevel(self.master)
        win.title("Редактировать урок")
        win.geometry("620x240")

        tk.Label(win, text="Раздел / предмет:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        sections = ["РО 6.1", "РО 6.2", "РО 6.3"] + [r[0] for r in fetch_all("SELECT title FROM ro_sections ORDER BY title")]
        combo_section = ttk.Combobox(win, values=sections)
        combo_section.grid(row=0, column=1, sticky="we", padx=6)
        combo_section.set(item[1])

        tk.Label(win, text="Номер:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        ent_num = tk.Entry(win); ent_num.grid(row=1, column=1, sticky="we", padx=6)
        ent_num.insert(0, item[2])

        tk.Label(win, text="Тема / критерии:").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        ent_crit = tk.Entry(win); ent_crit.grid(row=2, column=1, sticky="we", padx=6)
        ent_crit.insert(0, item[3])

        tk.Label(win, text="Часы:").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        ent_hours = tk.Entry(win); ent_hours.grid(row=3, column=1, sticky="we", padx=6)
        ent_hours.insert(0, item[4])

        tk.Label(win, text="Тип:").grid(row=4, column=0, sticky="e", padx=6, pady=6)
        combo_type = ttk.Combobox(win, values=["комбинированный", "практический"])
        combo_type.grid(row=4, column=1, sticky="we", padx=6)
        combo_type.set(item[5])

        def do_save():
            """Сохранить изменения урока."""
            section = combo_section.get().strip()
            if not section:
                messagebox.showerror("Ошибка", "Раздел обязателен")
                return
            try:
                number = int(ent_num.get())
                hours = int(ent_hours.get())
            except:
                messagebox.showerror("Ошибка", "Номер и Часы должны быть числами")
                return
            title = ent_crit.get().strip()
            ro_id = self.get_or_create_section_simple(section)
            execute("""UPDATE lessons SET ro_id=%s, number=%s, criteria=%s, total_hours=%s, type=%s WHERE id=%s""",
                    (ro_id, number, title, hours, combo_type.get(), lesson_id))
            win.destroy()
            self.lessons_load()

        tk.Button(win, text="Сохранить", command=do_save).grid(row=5, column=0, columnspan=2, pady=10)

    def lessons_delete(self):
        """Удалить выбранный урок после подтверждения."""
        sel = self.lessons_tree.selection()
        if not sel:
            messagebox.showwarning("Ошибка", "Выберите запись")
            return
        if not messagebox.askyesno("Подтвердить", "Удалить урок?"):
            return
        lesson_id = self.lessons_tree.item(sel[0])['values'][0]
        execute("DELETE FROM lessons WHERE id=%s", (lesson_id,))
        self.lessons_load()

    # ---------------- teachers tab ----------------
    def create_teachers_tab(self):
        """Создать вкладку Педагоги."""
        tab = ttk.Frame(self.tab_control)
        self.tab_control.add(tab, text="Педагоги")
        self.tabs['teachers'] = tab

        cols = ("id", "name", "position")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        for c, txt in zip(cols, ["ID", "ФИО", "Должность"]):
            tree.heading(c, text=txt)
            tree.column(c, width=200)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.teachers_tree = tree

        # кнопки управления
        f = tk.Frame(tab)
        f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Добавить", command=self.teachers_add, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Редактировать", command=self.teachers_edit, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Удалить", command=self.teachers_delete, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Обновить", command=self.teachers_load, width=14).pack(side=tk.LEFT, padx=5)
        self.teachers_load()

    def teachers_load(self):
        """Загрузить список педагогов."""
        for i in self.teachers_tree.get_children(): self.teachers_tree.delete(i)
        rows = fetch_all("SELECT id, full_name, position FROM teachers ORDER BY id DESC")
        for r in rows: self.teachers_tree.insert("", tk.END, values=r)

    def teachers_add(self):
        """Окно добавления педагога."""
        win = tk.Toplevel(self.master); win.title("Добавить педагога")
        tk.Label(win, text="ФИО:").grid(row=0, column=0); ent_name = tk.Entry(win); ent_name.grid(row=0, column=1)
        tk.Label(win, text="Должность:").grid(row=1, column=0); ent_pos = tk.Entry(win); ent_pos.grid(row=1, column=1)
        def do():
            if not ent_name.get().strip(): messagebox.showerror("Ошибка","ФИО обязательно"); return
            execute("INSERT INTO teachers (full_name, position) VALUES (%s,%s)", (ent_name.get().strip(), ent_pos.get().strip()))
            win.destroy(); self.teachers_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=2, column=0, columnspan=2, pady=8)

    def teachers_edit(self):
        """Окно редактирования педагога."""
        sel = self.teachers_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.teachers_tree.item(sel[0])['values']; tid = item[0]
        win = tk.Toplevel(self.master); win.title("Редактировать педагога")
        tk.Label(win, text="ФИО:").grid(row=0, column=0); ent_name = tk.Entry(win); ent_name.grid(row=0, column=1); ent_name.insert(0, item[1])
        tk.Label(win, text="Должность:").grid(row=1, column=0); ent_pos = tk.Entry(win); ent_pos.grid(row=1, column=1); ent_pos.insert(0, item[2])
        def do():
            execute("UPDATE teachers SET full_name=%s, position=%s WHERE id=%s", (ent_name.get().strip(), ent_pos.get().strip(), tid))
            win.destroy(); self.teachers_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=2, column=0, columnspan=2, pady=8)

    def teachers_delete(self):
        """Удалить педагога после подтверждения."""
        sel = self.teachers_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        if not messagebox.askyesno("Подтвердить","Удалить педагога?"): return
        tid = self.teachers_tree.item(sel[0])['values'][0]
        execute("DELETE FROM teachers WHERE id=%s", (tid,))
        self.teachers_load()

    # ---------------- students tab ----------------
    def create_students_tab(self):
        """Создать вкладку Ученики."""
        tab = ttk.Frame(self.tab_control); self.tab_control.add(tab, text="Ученики"); self.tabs['students'] = tab
        cols = ("id", "name", "birthdate", "class")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        for c, txt in zip(cols, ["ID", "ФИО", "Дата рожд.", "Группа"]):
            tree.heading(c, text=txt); tree.column(c, width=200)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.students_tree = tree
        f = tk.Frame(tab); f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Добавить", command=self.students_add, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Редактировать", command=self.students_edit, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Удалить", command=self.students_delete, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Обновить", command=self.students_load, width=14).pack(side=tk.LEFT, padx=5)
        self.students_load()

    def students_load(self):
        """Загрузить список учеников."""
        for i in self.students_tree.get_children(): self.students_tree.delete(i)
        rows = fetch_all("SELECT id, full_name, birthdate, class FROM students ORDER BY id DESC")
        for r in rows: self.students_tree.insert("", tk.END, values=r)

    def students_add(self):
        """Окно добавления ученика."""
        win = tk.Toplevel(self.master); win.title("Добавить ученика")
        tk.Label(win, text="ФИО:").grid(row=0,column=0); ent_name = tk.Entry(win); ent_name.grid(row=0,column=1)
        tk.Label(win, text="Дата рождения (YYYY-MM-DD):").grid(row=1,column=0); ent_bd = tk.Entry(win); ent_bd.grid(row=1,column=1)
        tk.Label(win, text="Класс:").grid(row=2,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=2,column=1)
        def do():
            name=ent_name.get().strip()
            if not name: messagebox.showerror("Ошибка","ФИО обязательно"); return
            bd = ent_bd.get().strip()
            try:
                if bd: datetime.strptime(bd, "%Y-%m-%d")
            except:
                messagebox.showerror("Ошибка","Дата в формате YYYY-MM-DD"); return
            execute("INSERT INTO students (full_name, birthdate, class) VALUES (%s,%s,%s)", (name, bd if bd else None, ent_cl.get().strip()))
            win.destroy(); self.students_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=3,column=0,columnspan=2,pady=8)

    def students_edit(self):
        """Окно редактирования ученика."""
        sel = self.students_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.students_tree.item(sel[0])['values']; sid=item[0]
        win = tk.Toplevel(self.master); win.title("Редактировать ученика")
        tk.Label(win, text="ФИО:").grid(row=0,column=0); ent_name = tk.Entry(win); ent_name.grid(row=0,column=1); ent_name.insert(0,item[1])
        tk.Label(win, text="Дата рождения (YYYY-MM-DD):").grid(row=1,column=0); ent_bd = tk.Entry(win); ent_bd.grid(row=1,column=1); ent_bd.insert(0,item[2] or "")
        tk.Label(win, text="Класс:").grid(row=2,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=2,column=1); ent_cl.insert(0,item[3] or "")
        def do():
            bd = ent_bd.get().strip()
            if bd:
                try: datetime.strptime(bd, "%Y-%m-%d")
                except: messagebox.showerror("Ошибка","Дата в формате YYYY-MM-DD"); return
            execute("UPDATE students SET full_name=%s, birthdate=%s, class=%s WHERE id=%s", (ent_name.get().strip(), bd if bd else None, ent_cl.get().strip(), sid))
            win.destroy(); self.students_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=3,column=0,columnspan=2,pady=8)

    def students_delete(self):
        """Удалить ученика после подтверждения."""
        sel = self.students_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        if not messagebox.askyesno("Подтвердить","Удалить ученика?"): return
        sid = self.students_tree.item(sel[0])['values'][0]
        execute("DELETE FROM students WHERE id=%s", (sid,))
        self.students_load()

    # ---------------- class_plans tab ----------------
    def create_class_plans_tab(self):
        """Создать вкладку Планы группы."""
        tab = ttk.Frame(self.tab_control); self.tab_control.add(tab, text="Планы группы"); self.tabs['class_plans'] = tab
        cols = ("id", "teacher", "class", "year", "file")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=14)
        headers = ["ID","Педагог","Группа","Год","Файл"]
        for c, h in zip(cols, headers):
            tree.heading(c, text=h); tree.column(c, width=200)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.class_plans_tree = tree
        f = tk.Frame(tab); f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Добавить", command=self.class_plans_add, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Редактировать", command=self.class_plans_edit, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Удалить", command=self.class_plans_delete, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Обновить", command=self.class_plans_load, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Скачать файл", command=self.class_plans_download, width=14).pack(side=tk.LEFT, padx=5)
        self.class_plans_load()

    def class_plans_load(self):
        """Загрузить планы групп."""
        for i in self.class_plans_tree.get_children(): self.class_plans_tree.delete(i)
        rows = fetch_all("""
            SELECT cp.id, t.full_name, cp.class, cp.year, cp.file_path
            FROM class_plans cp
            LEFT JOIN teachers t ON t.id = cp.teacher_id
            ORDER BY cp.id DESC
        """)
        for r in rows: self.class_plans_tree.insert("", tk.END, values=r)

    def class_plans_add(self):
        """Окно добавления плана класса."""
        win = tk.Toplevel(self.master); win.title("Добавить план класса")
        tk.Label(win, text="Педагог:").grid(row=0,column=0); teachers = [r[1] for r in fetch_all("SELECT id, full_name FROM teachers")]; combo = ttk.Combobox(win, values=teachers); combo.grid(row=0,column=1)
        tk.Label(win, text="Класс:").grid(row=1,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=1,column=1)
        tk.Label(win, text="Год:").grid(row=2,column=0); ent_year = tk.Entry(win); ent_year.grid(row=2,column=1)
        tk.Label(win, text="Файл (pdf/docx) (необязательно):").grid(row=3,column=0); ent_file = tk.Entry(win); ent_file.grid(row=3,column=1)
        def browse():
            # выбрать файл и показать только имя
            p = filedialog.askopenfilename(filetypes=[("PDF files","*.pdf"),("Word files","*.docx"),("All files","*.*")])
            if p: ent_file.delete(0,tk.END); ent_file.insert(0, os.path.basename(p))
        tk.Button(win, text="Обзор...", command=browse).grid(row=3,column=2)
        def do():
            # сохранить запись плана
            teacher_name = combo.get().strip()
            teacher_id = None
            if teacher_name:
                row = fetch_all("SELECT id FROM teachers WHERE full_name=%s", (teacher_name,))
                if row: teacher_id = row[0][0]
            year = ent_year.get().strip()
            if year and not year.isdigit(): messagebox.showerror("Ошибка","Год числом"); return
            execute("INSERT INTO class_plans (teacher_id, class, year, file_path) VALUES (%s,%s,%s,%s)", (teacher_id, ent_cl.get().strip(), int(year) if year else None, ent_file.get().strip() or None))
            win.destroy(); self.class_plans_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=4,column=0,columnspan=3,pady=8)

    def class_plans_edit(self):
        """Окно редактирования плана класса."""
        sel = self.class_plans_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.class_plans_tree.item(sel[0])['values']; pid=item[0]
        win = tk.Toplevel(self.master); win.title("Редактировать план")
        teachers = [r[1] for r in fetch_all("SELECT id, full_name FROM teachers")]
        tk.Label(win, text="Педагог:").grid(row=0,column=0); combo = ttk.Combobox(win, values=teachers); combo.grid(row=0,column=1); combo.set(item[1] or "")
        tk.Label(win, text="Класс:").grid(row=1,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=1,column=1); ent_cl.insert(0,item[2] or "")
        tk.Label(win, text="Год:").grid(row=2,column=0); ent_year = tk.Entry(win); ent_year.grid(row=2,column=1); ent_year.insert(0,item[3] or "")
        tk.Label(win, text="Файл:").grid(row=3,column=0); ent_file = tk.Entry(win); ent_file.grid(row=3,column=1); ent_file.insert(0,item[4] or "")
        def browse():
            p = filedialog.askopenfilename(filetypes=[("PDF files","*.pdf"),("Word files","*.docx"),("All files","*.*")])
            if p: ent_file.delete(0,tk.END); ent_file.insert(0, os.path.basename(p))
        tk.Button(win, text="Обзор...", command=browse).grid(row=3,column=2)
        def do():
            # обновить запись плана
            teacher_name = combo.get().strip(); teacher_id = None
            if teacher_name:
                row = fetch_all("SELECT id FROM teachers WHERE full_name=%s", (teacher_name,))
                if row: teacher_id = row[0][0]
            year = ent_year.get().strip()
            if year and not year.isdigit(): messagebox.showerror("Ошибка","Год числом"); return
            execute("UPDATE class_plans SET teacher_id=%s, class=%s, year=%s, file_path=%s WHERE id=%s", (teacher_id, ent_cl.get().strip(), int(year) if year else None, ent_file.get().strip() or None, pid))
            win.destroy(); self.class_plans_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=4,column=0,columnspan=3,pady=8)

    def class_plans_delete(self):
        """Удалить план класса."""
        sel = self.class_plans_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        if not messagebox.askyesno("Подтвердить","Удалить план?"): return
        pid = self.class_plans_tree.item(sel[0])['values'][0]
        execute("DELETE FROM class_plans WHERE id=%s", (pid,))
        self.class_plans_load()

    def class_plans_download(self):
        """Скачать файл плана (показать диалог сохранения)."""
        sel = self.class_plans_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.class_plans_tree.item(sel[0])['values']
        file_name = item[4]
        if not file_name:
            messagebox.showinfo("Инфо", "Файл не указан")
            return
        # показать диалог сохранения с предложенным именем
        dest = filedialog.asksaveasfilename(initialfile=file_name, defaultextension=os.path.splitext(file_name)[1] or "")
        if dest:
            # здесь предполагается, что файлы хранятся отдельно; просто создаём пустой файл как заглушку
            try:
                with open(dest, "wb") as f:
                    f.write(b"")  # заглушка, реальная логика копирования файла зависит от хранения
                messagebox.showinfo("Готово", "Файл сохранён")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {e}")

    # ---------------- social_passport tab ----------------
    def create_social_passport_tab(self):
        """Создать вкладку Социальный паспорт (заглушка интерфейса)."""
        tab = ttk.Frame(self.tab_control); self.tab_control.add(tab, text="Соц. паспорт"); self.tabs['social_passport'] = tab
        cols = ("id", "class", "year", "total", "full_families", "low_income", "disabilities", "orphaned", "many_children")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=14)
        headers = ["ID","Класс","Год","Всего","Полные семьи","Малоимущие","Инвалидность","Сироты","Многодетные"]
        for c, h in zip(cols, headers):
            tree.heading(c, text=h); tree.column(c, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.social_tree = tree
        f = tk.Frame(tab); f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Обновить", command=self.social_load, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Добавить (через SQL)", command=self.social_add_prompt, width=20).pack(side=tk.LEFT, padx=5)
        self.social_load()

    def social_load(self):
        """Загрузить записи социального паспорта."""
        for i in self.social_tree.get_children(): self.social_tree.delete(i)
        rows = fetch_all("SELECT id, class, year, total_students, full_families, low_income, disabilities, orphaned, many_children FROM social_passport ORDER BY id DESC")
        for r in rows: self.social_tree.insert("", tk.END, values=r)

    def social_add_prompt(self):
        """Простая форма добавления записи соц. паспорта (минимальная)."""
        win = tk.Toplevel(self.master); win.title("Добавить соц. паспорт")
        tk.Label(win, text="Класс:").grid(row=0,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=0,column=1)
        tk.Label(win, text="Год:").grid(row=1,column=0); ent_year = tk.Entry(win); ent_year.grid(row=1,column=1)
        tk.Label(win, text="Всего учеников:").grid(row=2,column=0); ent_total = tk.Entry(win); ent_total.grid(row=2,column=1)
        def do():
            year = ent_year.get().strip()
            if year and not year.isdigit(): messagebox.showerror("Ошибка","Год числом"); return
            execute("INSERT INTO social_passport (class, year, total_students) VALUES (%s,%s,%s)", (ent_cl.get().strip(), int(year) if year else None, int(ent_total.get().strip()) if ent_total.get().strip().isdigit() else None))
            win.destroy(); self.social_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=3,column=0,columnspan=2,pady=8)

    # ---------------- grade_reports tab ----------------
    def create_grade_reports_tab(self):
        """Создать вкладку Табели/Оценки."""
        tab = ttk.Frame(self.tab_control); self.tab_control.add(tab, text="Успеваемость"); self.tabs['grade_reports'] = tab
        cols = ("id", "student", "subject", "s1", "s2", "final")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=14)
        headers = ["ID","Ученик","Предмет","Семестр 1","Семестр 2","Итог"]
        for c, h in zip(cols, headers):
            tree.heading(c, text=h); tree.column(c, width=140)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.grades_tree = tree
        f = tk.Frame(tab); f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Добавить", command=self.grade_add, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Редактировать", command=self.grade_edit, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Удалить", command=self.grade_delete, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Обновить", command=self.grade_load, width=14).pack(side=tk.LEFT, padx=5)
        self.grade_load()

    def grade_load(self):
        """Загрузить оценки из БД."""
        for i in self.grades_tree.get_children(): self.grades_tree.delete(i)
        rows = fetch_all("""
            SELECT gr.id, s.full_name, gr.subject, gr.s1, gr.s2, gr.final_grade
            FROM grade_reports gr
            LEFT JOIN students s ON s.id = gr.student_id
            ORDER BY gr.id DESC
        """)
        for r in rows: self.grades_tree.insert("", tk.END, values=r)

    def grade_add(self):
        """Окно добавления оценки."""
        win = tk.Toplevel(self.master); win.title("Добавить оценку")
        students = [r[1] for r in fetch_all("SELECT id, full_name FROM students")]
        tk.Label(win, text="Ученик:").grid(row=0,column=0); combo = ttk.Combobox(win, values=students); combo.grid(row=0,column=1)
        tk.Label(win, text="Предмет:").grid(row=1,column=0); ent_sub = tk.Entry(win); ent_sub.grid(row=1,column=1)
        tk.Label(win, text="Семестр 1:").grid(row=2,column=0); ent_s1 = tk.Entry(win); ent_s1.grid(row=2,column=1)
        tk.Label(win, text="Семестр 2:").grid(row=3,column=0); ent_s2 = tk.Entry(win); ent_s2.grid(row=3,column=1)
        def do():
            student_name = combo.get().strip(); student_id = None
            if student_name:
                row = fetch_all("SELECT id FROM students WHERE full_name=%s", (student_name,))
                if row: student_id = row[0][0]
            s1 = ent_s1.get().strip(); s2 = ent_s2.get().strip()
            s1v = int(s1) if s1.isdigit() else None
            s2v = int(s2) if s2.isdigit() else None
            final = None
            if s1v is not None and s2v is not None:
                final = round((s1v + s2v) / 2)
            elif s1v is not None:
                final = s1v
            elif s2v is not None:
                final = s2v
            execute("INSERT INTO grade_reports (student_id, subject, s1, s2, final_grade) VALUES (%s,%s,%s,%s,%s)", (student_id, ent_sub.get().strip(), s1v, s2v, final))
            win.destroy(); self.grade_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=4,column=0,columnspan=2,pady=8)

    def grade_edit(self):
        """Окно редактирования оценки."""
        sel = self.grades_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.grades_tree.item(sel[0])['values']; gid=item[0]
        win = tk.Toplevel(self.master); win.title("Редактировать оценку")
        students = [r[1] for r in fetch_all("SELECT id, full_name FROM students")]
        tk.Label(win, text="Ученик:").grid(row=0,column=0); combo = ttk.Combobox(win, values=students); combo.grid(row=0,column=1); combo.set(item[1] or "")
        tk.Label(win, text="Предмет:").grid(row=1,column=0); ent_sub = tk.Entry(win); ent_sub.grid(row=1,column=1); ent_sub.insert(0,item[2] or "")
        tk.Label(win, text="Семестр 1:").grid(row=2,column=0); ent_s1 = tk.Entry(win); ent_s1.grid(row=2,column=1); ent_s1.insert(0,item[3] or "")
        tk.Label(win, text="Семестр 2:").grid(row=3,column=0); ent_s2 = tk.Entry(win); ent_s2.grid(row=3,column=1); ent_s2.insert(0,item[4] or "")
        def do():
            student_name = combo.get().strip(); student_id = None
            if student_name:
                row = fetch_all("SELECT id FROM students WHERE full_name=%s", (student_name,))
                if row: student_id = row[0][0]
            s1 = ent_s1.get().strip(); s2 = ent_s2.get().strip()
            s1v = int(s1) if s1.isdigit() else None
            s2v = int(s2) if s2.isdigit() else None
            final = None
            if s1v is not None and s2v is not None:
                final = round((s1v + s2v) / 2)
            elif s1v is not None:
                final = s1v
            elif s2v is not None:
                final = s2v
            execute("UPDATE grade_reports SET student_id=%s, subject=%s, s1=%s, s2=%s, final_grade=%s WHERE id=%s", (student_id, ent_sub.get().strip(), s1v, s2v, final, gid))
            win.destroy(); self.grade_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=4,column=0,columnspan=2,pady=8)

    def grade_delete(self):
        """Удалить запись об оценке."""
        sel = self.grades_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        if not messagebox.askyesno("Подтвердить","Удалить запись?"): return
        gid = self.grades_tree.item(sel[0])['values'][0]
        execute("DELETE FROM grade_reports WHERE id=%s", (gid,))
        self.grade_load()

    # ---------------- exam_protocols tab ----------------
    def create_exam_protocols_tab(self):
        """Создать вкладку Протоколы экзаменов."""
        tab = ttk.Frame(self.tab_control); self.tab_control.add(tab, text="Протоколы экзаменов"); self.tabs['exam_protocols'] = tab
        cols = ("id", "teacher", "subject", "class", "date", "file")
        tree = ttk.Treeview(tab, columns=cols, show="headings", height=14)
        headers = ["ID","Педагог","Предмет","Класс","Дата","Файл"]
        for c, h in zip(cols, headers):
            tree.heading(c, text=h); tree.column(c, width=140)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.exam_tree = tree
        f = tk.Frame(tab); f.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(f, text="Добавить", command=self.exam_add, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Редактировать", command=self.exam_edit, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Удалить", command=self.exam_delete, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Обновить", command=self.exam_load, width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(f, text="Скачать файл", command=self.exam_download, width=14).pack(side=tk.LEFT, padx=5)
        self.exam_load()

    def exam_load(self):
        """Загрузить протоколы экзаменов."""
        for i in self.exam_tree.get_children(): self.exam_tree.delete(i)
        rows = fetch_all("""
            SELECT ep.id, t.full_name, ep.subject, ep.class, ep.date, ep.file_path
            FROM exam_protocols ep
            LEFT JOIN teachers t ON t.id = ep.teacher_id
            ORDER BY ep.id DESC
        """)
        for r in rows: self.exam_tree.insert("", tk.END, values=r)

    def exam_add(self):
        """Окно добавления протокола экзамена."""
        win = tk.Toplevel(self.master); win.title("Добавить протокол")
        tk.Label(win, text="Педагог:").grid(row=0,column=0); teachers = [r[1] for r in fetch_all("SELECT id, full_name FROM teachers")]; combo = ttk.Combobox(win, values=teachers); combo.grid(row=0,column=1)
        tk.Label(win, text="Предмет:").grid(row=1,column=0); ent_sub = tk.Entry(win); ent_sub.grid(row=1,column=1)
        tk.Label(win, text="Класс:").grid(row=2,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=2,column=1)
        tk.Label(win, text="Дата (YYYY-MM-DD):").grid(row=3,column=0); ent_date = tk.Entry(win); ent_date.grid(row=3,column=1)
        tk.Label(win, text="Файл (необязательно):").grid(row=4,column=0); ent_file = tk.Entry(win); ent_file.grid(row=4,column=1)
        def browse():
            p = filedialog.askopenfilename(filetypes=[("PDF files","*.pdf"),("Word files","*.docx"),("All files","*.*")])
            if p: ent_file.delete(0,tk.END); ent_file.insert(0, os.path.basename(p))
        tk.Button(win, text="Обзор...", command=browse).grid(row=4,column=2)
        def do():
            teacher_name = combo.get().strip(); teacher_id = None
            if teacher_name:
                row = fetch_all("SELECT id FROM teachers WHERE full_name=%s", (teacher_name,))
                if row: teacher_id = row[0][0]
            d = ent_date.get().strip()
            if d:
                try: datetime.strptime(d, "%Y-%m-%d")
                except: messagebox.showerror("Ошибка","Дата в формате YYYY-MM-DD"); return
            execute("INSERT INTO exam_protocols (teacher_id, subject, class, date, file_path) VALUES (%s,%s,%s,%s,%s)", (teacher_id, ent_sub.get().strip(), ent_cl.get().strip(), d if d else None, ent_file.get().strip() or None))
            win.destroy(); self.exam_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=5,column=0,columnspan=3,pady=8)

    def exam_edit(self):
        """Окно редактирования протокола."""
        sel = self.exam_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.exam_tree.item(sel[0])['values']; eid=item[0]
        win = tk.Toplevel(self.master); win.title("Редактировать протокол")
        teachers = [r[1] for r in fetch_all("SELECT id, full_name FROM teachers")]
        tk.Label(win, text="Педагог:").grid(row=0,column=0); combo = ttk.Combobox(win, values=teachers); combo.grid(row=0,column=1); combo.set(item[1] or "")
        tk.Label(win, text="Предмет:").grid(row=1,column=0); ent_sub = tk.Entry(win); ent_sub.grid(row=1,column=1); ent_sub.insert(0,item[2] or "")
        tk.Label(win, text="Класс:").grid(row=2,column=0); ent_cl = tk.Entry(win); ent_cl.grid(row=2,column=1); ent_cl.insert(0,item[3] or "")
        tk.Label(win, text="Дата (YYYY-MM-DD):").grid(row=3,column=0); ent_date = tk.Entry(win); ent_date.grid(row=3,column=1); ent_date.insert(0,item[4] or "")
        tk.Label(win, text="Файл:").grid(row=4,column=0); ent_file = tk.Entry(win); ent_file.grid(row=4,column=1); ent_file.insert(0,item[5] or "")
        def browse():
            p = filedialog.askopenfilename(filetypes=[("PDF files","*.pdf"),("Word files","*.docx"),("All files","*.*")])
            if p: ent_file.delete(0,tk.END); ent_file.insert(0, os.path.basename(p))
        tk.Button(win, text="Обзор...", command=browse).grid(row=4,column=2)
        def do():
            teacher_name = combo.get().strip(); teacher_id = None
            if teacher_name:
                row = fetch_all("SELECT id FROM teachers WHERE full_name=%s", (teacher_name,))
                if row: teacher_id = row[0][0]
            d = ent_date.get().strip()
            if d:
                try: datetime.strptime(d, "%Y-%m-%d")
                except: messagebox.showerror("Ошибка","Дата в формате YYYY-MM-DD"); return
            execute("UPDATE exam_protocols SET teacher_id=%s, subject=%s, class=%s, date=%s, file_path=%s WHERE id=%s", (teacher_id, ent_sub.get().strip(), ent_cl.get().strip(), d if d else None, ent_file.get().strip() or None, eid))
            win.destroy(); self.exam_load()
        tk.Button(win, text="Сохранить", command=do).grid(row=5,column=0,columnspan=3,pady=8)

    def exam_delete(self):
        """Удалить протокол экзамена."""
        sel = self.exam_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        if not messagebox.askyesno("Подтвердить","Удалить протокол?"): return
        eid = self.exam_tree.item(sel[0])['values'][0]
        execute("DELETE FROM exam_protocols WHERE id=%s", (eid,))
        self.exam_load()

    def exam_download(self):
        """Скачать файл протокола (показать диалог сохранения)."""
        sel = self.exam_tree.selection()
        if not sel: messagebox.showwarning("Ошибка","Выберите строку"); return
        item = self.exam_tree.item(sel[0])['values']
        file_name = item[5]
        if not file_name:
            messagebox.showinfo("Инфо", "Файл не указан")
            return
        dest = filedialog.asksaveasfilename(initialfile=file_name, defaultextension=os.path.splitext(file_name)[1] or "")
        if dest:
            try:
                with open(dest, "wb") as f:
                    f.write(b"")  # заглушка
                messagebox.showinfo("Готово", "Файл сохранён")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {e}")

# ---------- Запуск приложения ----------
if __name__ == "__main__":
    # Создать таблицы при старте, если нужно
    try:
        create_tables_if_not_exist()
    except Exception as e:
        # Если не удалось подключиться к БД — показать ошибку и выйти
        print("Ошибка при инициализации БД:", e)
        sys.exit(1)

    root = tk.Tk()
    app = AdminApp(root)
    root.mainloop()