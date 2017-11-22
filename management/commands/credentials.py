import os
import sys

from simplecrypt import encrypt, decrypt

from ..base import BaseCommand

FILE_EXT = 'aes'


def create_decrypted(source_filename, dest_filename, passphrase):
    with open(source_filename, 'rb') as encrypred_file:
        with open(dest_filename, 'wb') as output:
            ciphertext = encrypred_file.read()
            plaintext = decrypt(passphrase, ciphertext)
            output.truncate()
            output.write(plaintext)


def create_encrypted(source_filename, dest_filename, passphrase):
    with open(source_filename, 'rb') as orig_file:
        with open(dest_filename, 'wb') as output:
            ciphertext = encrypt(passphrase, orig_file.read())
            output.truncate()
            output.write(ciphertext)


class Command(BaseCommand):
    def __init__(self):
        super(Command, self).__init__()

        from sgateway.app import get_application
        self.app = get_application()
        self.credentials_file_path = getattr(self.app, 'credentials_file_path', None)
        if not self.credentials_file_path:
            raise EnvironmentError("This command require credentials_file_path to be configured.")

    def add_arguments(self, parser):
        parser.add_argument('operation')
        parser.add_argument('--passphrase', help='Secret passphrase to use for encrypt/decrypt files')
        parser.add_argument('--override', action='store_true')

    def execute(self, **options):
        operation = options['operation']
        self.allow_override = options.get('override')
        raw_filename = self.credentials_file_path
        encrypted_filename = "%s.%s" % (raw_filename, FILE_EXT)

        operation_func = getattr(self, operation, None)

        if operation_func:
            passphrase = options['passphrase'] or input("Enter passphrase: ")
            operation_func(raw_filename, encrypted_filename, passphrase)
        else:
            print("Unknown operation: {}".format(operation))
            sys.exit(1)

    def decrypt(self, raw_filename, encrypted_filename, passphrase):
        if not os.path.exists(encrypted_filename):
            print("File with encrypred credentials doesn't exist: {}".format(encrypted_filename))
            sys.exit(1)

        if os.path.exists(raw_filename) and not self.allow_override:
            print("File with decrypred credentials already exists. Delete it or use '--override'.")
            sys.exit(1)

        create_decrypted(encrypted_filename, raw_filename, passphrase)

    def encrypt(self, raw_filename, encrypted_filename, passphrase):
        if not os.path.exists(raw_filename):
            print("Credentials file to be encrypted doesn't exist: {}".format(raw_filename))
            sys.exit(1)

        if os.path.exists(encrypted_filename) and not self.allow_override:
            print("Encrypted file already exists. Delete it or use '--override'.")
            sys.exit(1)

        create_encrypted(raw_filename, encrypted_filename, passphrase)
