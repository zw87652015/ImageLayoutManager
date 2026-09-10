import ast
from pathlib import Path
import re
import unittest


class WindowsInstallerTests(unittest.TestCase):
    def test_upgrade_removes_only_obsolete_root_qt_libraries(self):
        source = Path(__file__).with_name('build_installer_windows.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        assignment = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'iss_content' for target in node.targets)
        )
        template = ''.join(
            part.value for part in assignment.value.args[0].values
            if isinstance(part, ast.Constant)
        )
        section = re.search(r'\[InstallDelete\]\s*(.*?)(?=\n\s*\[|\Z)', template, re.S)
        self.assertIsNotNone(section, 'Upgrades must remove Qt DLLs no longer shipped by the installer')
        entries = [line.strip() for line in section.group(1).splitlines() if line.strip()]
        self.assertEqual(entries, [r'Type: files; Name: "{app}\_internal\Qt6*.dll"'])


if __name__ == '__main__':
    unittest.main()
