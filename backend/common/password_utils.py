import logging, re
from common.SecurityExceptions import SecurityValidationError

from password_strength import PasswordPolicy

try:
	_PASSWORD_STRENGTH_AVAILABLE = True
except ImportError:
	_PASSWORD_STRENGTH_AVAILABLE = False
_PASSWORD_STRENGTH_AVAILABLE = False


logger = logging.getLogger(__name__)

def validate_password_basic(password: str) -> str:
	"""Validate password strength requirements."""
	if not isinstance(password, str):
		raise SecurityValidationError("Password must be a string")

	# Check basic length requirements
	if len(password) < 8:
		raise SecurityValidationError("Password must be at least 8 characters long")

	if len(password) > 128:
		raise SecurityValidationError("Password must not exceed 128 characters")

	# Use password-strength library if available, otherwise fallback to basic checks
	logger.info(f"Validating password strength for: '{password}'")
	if _PASSWORD_STRENGTH_AVAILABLE:
		policy = PasswordPolicy.from_names(
			strength=0.5  # need a password that scores at least 0.5 with its strength
		)

		# Test the password
		issues = policy.test(password)
		logger.info(f"""Password "{password}"" validation issues: {issues}""")
		if issues:
			# Convert issues to readable error messages
			error_messages = []
			for issue in issues:
				if hasattr(issue, '__class__'):
					error_messages.append(str(issue))
			if error_messages:
				raise SecurityValidationError(f"Password is too weak: {', '.join(error_messages)}")
	else:
		# Fallback to basic validation
		# Check for at least one lowercase letter
		if not re.search(r'[a-z]', password):
			raise SecurityValidationError("Password must contain at least one lowercase letter")

		# Check for at least one uppercase letter or digit
		if not (re.search(r'[A-Z]', password) or re.search(r'[0-9]', password)):
			raise SecurityValidationError("Password must contain at least one uppercase letter or digit")

		# Check for common weak passwords
		weak_passwords = {
			"password", "password123", "12345678", "qwerty", "abc123", "letmein",
			"welcome", "monkey", "123456789", "password1", "admin", "administrator"
		}
		if password.lower() in weak_passwords:
			raise SecurityValidationError("Password is too common and easily guessable")

	return password

