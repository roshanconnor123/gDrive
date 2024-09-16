import os
import re
import threading

from .fs_constants import ARTWORK
from .fs_helpers import createSTRMContents
from ..threadpool.threadpool import ThreadPool
from ..library.library_editor import DatabaseEditor


class RemoteFileProcessor:

	def __init__(self, cloudService, fileOperations, settings, cache):
		self.cloudService = cloudService
		self.fileOperations = fileOperations
		self.settings = settings
		self.cache = cache
		self.dbEditor = DatabaseEditor()

	def processFiles(self, folder, folderSettings, syncRootPath, driveID, rootFolderID, threadCount, progressDialog=None):
		files = folder.files
		parentFolderID = folder.id
		dirPath = folder.localPath
		folderRestructure = folderSettings["folder_restructure"]
		fileRenaming = folderSettings["file_renaming"]
		videos = files.get("video")
		mediaAssets = files.get("media_assets")
		strm = files.get("strm")
		cachedFiles = []

		if strm:

			with ThreadPool(threadCount) as pool:
				[
					pool.submit(
						self._processSTRM,
						file,
						dirPath,
						driveID,
						rootFolderID,
						parentFolderID,
						cachedFiles,
						progressDialog,
					) for file in strm
				]

		if folderRestructure or fileRenaming:
			dirPath = os.path.join(syncRootPath, "[gDrive] Processing", os.path.relpath(dirPath, start=syncRootPath))
			folder.processingPath = dirPath
			originalFolder = False
		else:
			originalFolder = True

		if videos:

			with ThreadPool(threadCount) as pool:
				[
					pool.submit(
						self._processVideo,
						video,
						syncRootPath,
						dirPath,
						driveID,
						rootFolderID,
						parentFolderID,
						cachedFiles,
						originalFolder,
						progressDialog,
					) for video in videos
				]

		if mediaAssets:

			with ThreadPool(threadCount) as pool:
				[
					pool.submit(
						self._processMediaAssets,
						assets,
						syncRootPath,
						dirPath,
						driveID,
						rootFolderID,
						parentFolderID,
						cachedFiles,
						originalFolder,
						progressDialog,
					) for assetName, assets in mediaAssets.items() if assets
				]

		self.cache.addFiles(cachedFiles)

	def _processMediaAssets(self, mediaAssets, syncRootPath, dirPath, driveID, rootFolderID, parentFolderID, cachedFiles, originalFolder, progressDialog):

		for file in mediaAssets:
			fileID = file.id
			remoteName = file.name
			filePath = self.fileOperations.downloadFile(dirPath, remoteName, fileID, modifiedTime=file.modifiedTime, encrypted=file.encrypted)
			localName = os.path.basename(filePath)
			file.name = localName
			file = (
				driveID,
				rootFolderID,
				parentFolderID,
				fileID,
				filePath.replace(syncRootPath, "", 1) if not originalFolder else False,
				localName,
				remoteName,
				True,
				originalFolder,
			)
			cachedFiles.append(file)

			if progressDialog:
				progressDialog.processFile(remoteName)

	def _processSTRM(self, file, dirPath, driveID, rootFolderID, parentFolderID, cachedFiles, progressDialog):
		fileID = file.id
		remoteName = file.name
		filePath = self.fileOperations.downloadFile(dirPath, remoteName, fileID, modifiedTime=file.modifiedTime, encrypted=file.encrypted)
		localName = os.path.basename(filePath)
		file = (
			driveID,
			rootFolderID,
			parentFolderID,
			fileID,
			False,
			localName,
			remoteName,
			True,
			True,
		)
		cachedFiles.append(file)

		if progressDialog:
			progressDialog.processFile(remoteName)

	def _processVideo(self, file, syncRootPath, dirPath, driveID, rootFolderID, parentFolderID, cachedFiles, originalFolder, progressDialog):
		fileID = file.id
		remoteName = file.name
		filename = f"{file.basename}.strm"
		strmContent = createSTRMContents(driveID, fileID, file.encrypted, file.contents)
		filePath = self.fileOperations.createFile(dirPath, filename, strmContent, modifiedTime=file.modifiedTime, mode="w+")
		localName = os.path.basename(filePath)
		file.name = localName
		file_ = (
			driveID,
			rootFolderID,
			parentFolderID,
			fileID,
			filePath.replace(syncRootPath, "", 1) if not originalFolder else False,
			localName,
			remoteName,
			True,
			originalFolder,
		)
		cachedFiles.append(file_)

		if file.updateDBdata:
			self.dbEditor.processData(filePath, dirPath, localName)

		if progressDialog:
			progressDialog.processFile(remoteName)


class LocalFileProcessor:

	def __init__(self, cloudService, fileOperations, settings, cache):
		self.cloudService = cloudService
		self.fileOperations = fileOperations
		self.settings = settings
		self.cache = cache
		self.imdbLock = threading.Lock()

	def processFiles(self, folder, folderSettings, syncRootPath, threadCount, progressDialog=None):
		files = folder.files
		dirPath = folder.localPath
		processingPath = folder.processingPath
		videos = files.get("video")
		mediaAssets = files.get("media_assets")

		if progressDialog:
			strm = files.get("strm")

			if strm:
				progressDialog.incrementFiles(len(strm))

		if videos:
			folderRestructure = folderSettings["folder_restructure"]
			fileRenaming = folderSettings["file_renaming"]
			tmdbSettings = {"api_key": "98d275ee6cbf27511b53b1ede8c50c67"}

			for key, value in {"tmdb_language": "language", "tmdb_region": "region", "tmdb_adult": "include_adult"}.items():

				if folderSettings[key]:
					tmdbSettings[value] = folderSettings[key]

			with ThreadPool(threadCount) as pool:
				[
					pool.submit(
						self._processVideo,
						video,
						mediaAssets,
						syncRootPath,
						dirPath,
						processingPath,
						folderRestructure,
						fileRenaming,
						tmdbSettings,
						progressDialog,
					) for video in videos
				]

		if mediaAssets:

			with ThreadPool(threadCount) as pool:
				[
					pool.submit(
						self._processMediaAssets,
						assets,
						syncRootPath,
						dirPath,
						processingPath,
						None,
						True,
						True,
						progressDialog,
					) for assetName, assets in mediaAssets.items() if assets
				]

	def _processMediaAssets(self, mediaAssets, syncRootPath, dirPath, processingPath, videoFilename, originalName, originalFolder, progressDialog):

		for file in list(mediaAssets):
			fileID = file.id
			remoteName = file.name
			assetType = file.type
			fileExtension = f".{file.extension}"

			if originalName:
				filename = remoteName
			else:

				if assetType == "subtitles":
					language = ""

					if file.language:
						language += f".{file.language}"

					if re.search("forced\.[\w]*$", remoteName, re.IGNORECASE):
						language += ".Forced"

					fileExtension = f"{language}{fileExtension}"

				elif assetType in ARTWORK:
					fileExtension = f"-{assetType}{fileExtension}"

				filename = f"{videoFilename}{fileExtension}"

			filePath = os.path.join(processingPath, remoteName)
			filePath = self.fileOperations.renameFile(syncRootPath, filePath, dirPath, filename)
			mediaAssets.remove(file)

			if progressDialog:
				progressDialog.processRenamedFile(file.name)

			file = {
				"local_path": filePath.replace(syncRootPath, "", 1) if not originalFolder else False,
				"local_name": os.path.basename(filePath),
				"original_name": originalName,
				"original_folder": originalFolder,
			}
			self.cache.updateFile(file, fileID)

	def _processVideo(self, file, mediaAssets, syncRootPath, dirPath, processingPath, folderRestructure, fileRenaming, tmdbSettings, progressDialog):
		fileID = file.id
		mediaType = file.media
		ptnName = file.ptnName
		filename = f"{file.basename}.strm"
		filePath = os.path.join(processingPath, filename)
		originalName = originalFolder = True
		newFilename = None

		if mediaType in ("episode", "movie"):
			modifiedName = file.formatName(tmdbSettings, self.imdbLock)

			if modifiedName:
				newFilename = modifiedName.get("filename")

			if newFilename:

				if fileRenaming:
					filename = f"{newFilename}.strm"
					originalName = False

				if folderRestructure:
					originalFolder = False

					if mediaType == "movie":
						dirPath = os.path.join(syncRootPath, "[gDrive] Movies", newFilename)
					else:
						dirPath = os.path.join(
							syncRootPath,
							"[gDrive] Series",
							f"{modifiedName['title']} ({modifiedName['year']})",
							f"Season {file.season}",
						)

		if ptnName in mediaAssets:
			self._processMediaAssets(
				mediaAssets[ptnName],
				syncRootPath,
				dirPath,
				processingPath,
				newFilename,
				originalName,
				originalFolder,
				progressDialog,
			)

		filePath = self.fileOperations.renameFile(syncRootPath, filePath, dirPath, filename)

		if progressDialog:
			progressDialog.processRenamedFile(file.name)

		file = {
			"local_path": filePath.replace(syncRootPath, "", 1) if not originalFolder else False,
			"local_name": os.path.basename(filePath),
			"original_name": originalName,
			"original_folder": originalFolder,
		}
		self.cache.updateFile(file, fileID)