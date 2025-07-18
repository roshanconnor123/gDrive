# http://stackoverflow.com/questions/6425131/encrpyt-decrypt-data-in-python-with-salt

import os
import base64
import random
import string
import struct
import hashlib

try:
	from Cryptodome.Cipher import AES
except ImportError:
	from Crypto.Cipher import AES


class Encryptor:
	# Salt size in bytes
	SALT_SIZE = 32
	# Number of iterations in the key generation
	NUMBER_OF_ITERATIONS = 20
	# The size multiple required for AES
	AES_MULTIPLE = 16

	def __init__(self, saltFile=None, saltPassword=None, salt=None):
		self._setup(saltFile, saltPassword, salt)

	def decryptFile(self, inFilename, outFilename=None, chunkSize=24 * 1024):
		""" Decrypts a file using AES (CBC mode) with the
			given key. Parameters are similar to encryptFile,
			with one difference: outFilename, if not supplied
			will be inFilename without its last extension
			(i.e. if inFilename is 'aaa.zip.enc' then
			outFilename will be 'aaa.zip')
		"""

		if not outFilename:
			outFilename = os.path.splitext(inFilename)[0]

		with open(inFilename, "rb") as inFile:
			origSize = struct.unpack("<Q", inFile.read(struct.calcsize("Q")))[0]
			decryptor = AES.new(self.key, AES.MODE_ECB)

			with open(outFilename, "wb") as outFile:

				while True:
					chunk = inFile.read(chunkSize)

					if len(chunk) == 0:
						break

					outFile.write(decryptor.decrypt(chunk))

				outFile.truncate(origSize)

	def decryptStream(self, response, filePath, chunkSize=24 * 1024):
		origSize = struct.unpack("<Q", response.read(struct.calcsize("Q")))[0]
		decryptor = AES.new(self.key, AES.MODE_ECB)

		with open(filePath, "wb") as outFile:

			while chunk := response.read(chunkSize):
				outFile.write(decryptor.decrypt(chunk))

			outFile.truncate(origSize)

	def decryptStreamChunk(self, response, wfile, startOffset, chunkSize=24 * 1024):
		origSize = struct.unpack("<Q", response.read(struct.calcsize("Q")))[0]
		decryptor = AES.new(self.key, AES.MODE_ECB)
		count = 0

		while chunk := response.read(chunkSize):
			responseChunk = decryptor.decrypt(chunk)
			count += 1

			if count == 1 and startOffset != 0:
				wfile.write(responseChunk[startOffset:])
			elif len(chunk) < len(responseChunk.strip()):
				wfile.write(responseChunk.strip())
			else:
				wfile.write(responseChunk)

	def decryptString(self, string):
		decryptor = AES.new(self.key, AES.MODE_ECB)

		if len(string) == 0:
			return

		try:
			return decryptor.decrypt(base64.b64decode(string.replace("---", "/").encode("utf-8"))).rstrip().decode("utf-8")
		except Exception:
			return string

	def encryptFile(self, inFilename, outFilename=None, chunkSize=64 * 1024):
		""" Encrypts a file using AES (CBC mode) with the
			given key.

			key:
				The encryption key - a string that must be
				either 16, 24 or 32 bytes long. Longer keys
				are more secure.

			inFilename:
				Name of the input file

			outFilename:
				If None, '<inFilename>.enc' will be used.

			chunkSize:
				Sets the size of the chunk which the function
				uses to read and encrypt the file. Larger chunk
				sizes can be faster for some files and machines.
				chunksize must be divisible by 16.
		"""

		if not outFilename:
			outFilename = inFilename + ".enc"

		encryptor = AES.new(self.key, AES.MODE_ECB)
		fileSize = os.path.getsize(inFilename)

		with open(inFilename, "rb") as inFile:

			with open(outFilename, "wb") as outFile:
				outFile.write(struct.pack("<Q", fileSize))

				while True:
					chunk = inFile.read(chunkSize)

					if len(chunk) == 0:
						break
					elif len(chunk) % 16 != 0:
						chunk += b" " * (16 - len(chunk) % 16)

					outFile.write(encryptor.encrypt(chunk))

	def encryptFilename(filename):
		return base64.b64encode(filename)

	def encryptString(self, string):
		encryptor = AES.new(self.key, AES.MODE_ECB)

		if len(string) == 0:
			return
		elif len(string) % 16 != 0:
			string += " " * (16 - len(string) % 16)

		return base64.b64encode(encryptor.encrypt(string.encode("utf-8"))).replace(b"/", b"---").decode("utf-8")

	def _generateKey(self, password, iterations=NUMBER_OF_ITERATIONS):

		if not iterations > 0:
			return

		key = password + self.salt

		for i in range(iterations):
			key = hashlib.sha256(key).digest()

		return key

	def _generateSalt(self, size=SALT_SIZE):
		return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(size)).encode("utf-8")

	def _setup(self, saltFile=None, saltPassword=None, salt=None):

		if salt:
			self.salt = salt.encode("utf-8")
		else:

			try:

				try:

					with open(saltFile, "rb") as salt:
						self.salt = salt.read()

				except Exception:

					with open(saltFile, "wb") as salt:
						self.salt = self._generateSalt()
						salt.write(self.salt)

			except Exception:
				return

		if saltPassword:
			self.key = self._generateKey(saltPassword.encode("utf-8"))
