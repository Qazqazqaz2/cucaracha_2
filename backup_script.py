#!/usr/bin/env python3
"""
Скрипт для автоматического бэкапа проекта в GitHub
"""

import os
import subprocess
import datetime
import sys
from pathlib import Path

def run_command(command, cwd=None):
    """Выполняет команду и возвращает результат"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Ошибка выполнения команды: {command}")
        print(f"Код ошибки: {e.returncode}")
        print(f"Вывод ошибки: {e.stderr}")
        return None

def check_git_status():
    """Проверяет статус Git репозитория"""
    print("Проверка статуса Git...")
    
    # Проверяем, что мы в Git репозитории
    if not os.path.exists('.git'):
        print("Ошибка: Не найден Git репозиторий")
        return False
    
    # Проверяем статус
    status = run_command("git status --porcelain")
    if status is None:
        return False
    
    if not status:
        print("Нет изменений для коммита")
        return False
    
    print("Найдены изменения:")
    print(status)
    return True

def create_backup():
    """Создает бэкап проекта"""
    print("Создание бэкапа...")
    
    # Получаем текущую дату и время
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Проверяем статус
    if not check_git_status():
        return False
    
    # Добавляем все изменения
    print("Добавление изменений...")
    result = run_command("git add .")
    if result is None:
        return False
    
    # Создаем коммит
    commit_message = f"Backup {timestamp}"
    print(f"Создание коммита: {commit_message}")
    result = run_command(f'git commit -m "{commit_message}"')
    if result is None:
        return False
    
    # Отправляем в GitHub
    print("Отправка в GitHub...")
    result = run_command("git push origin main")
    if result is None:
        return False
    
    print("✅ Бэкап успешно создан и отправлен в GitHub!")
    return True

def restore_from_backup():
    """Восстанавливает проект из последнего коммита"""
    print("Восстановление из бэкапа...")
    
    # Получаем последние изменения
    result = run_command("git pull origin main")
    if result is None:
        print("Ошибка при получении изменений из GitHub")
        return False
    
    print("✅ Проект восстановлен из последнего бэкапа!")
    return True

def show_backup_history():
    """Показывает историю бэкапов"""
    print("История бэкапов:")
    result = run_command("git log --oneline -10")
    if result:
        print(result)
    else:
        print("Ошибка при получении истории")

def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python backup_script.py backup     - создать бэкап")
        print("  python backup_script.py restore    - восстановить из бэкапа")
        print("  python backup_script.py history    - показать историю бэкапов")
        print("  python backup_script.py status     - показать статус")
        return
    
    command = sys.argv[1].lower()
    
    if command == "backup":
        create_backup()
    elif command == "restore":
        restore_from_backup()
    elif command == "history":
        show_backup_history()
    elif command == "status":
        check_git_status()
    else:
        print(f"Неизвестная команда: {command}")

if __name__ == "__main__":
    main()
