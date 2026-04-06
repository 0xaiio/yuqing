import axios from 'axios'

import type {
  CreateSourcePayload,
  FaceCluster,
  FaceThresholds,
  FaceTuningBundle,
  HealthStatus,
  ImportJob,
  PersonClusterCorrectionCandidate,
  PersonClusterCorrectionResult,
  PersonProfile,
  PersonSample,
  Photo,
  SearchQueryPayload,
  SearchResponse,
  Source,
  Video,
  VideoSearchResponse,
} from '../types'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'
).replace(/\/+$/, '')

const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 60000,
})

export { apiBaseUrl }

export async function getHealth(): Promise<HealthStatus> {
  const response = await api.get<HealthStatus>('/health')
  return response.data
}

export async function listSources(): Promise<Source[]> {
  const response = await api.get<Source[]>('/sources')
  return response.data
}

export async function createSource(payload: CreateSourcePayload): Promise<Source> {
  const response = await api.post<Source>('/sources', payload)
  return response.data
}

export async function importSource(sourceId: number, limit: number): Promise<ImportJob> {
  const response = await api.post<ImportJob>(`/sources/${sourceId}/import`, { limit })
  return response.data
}

export async function startSourceWatch(sourceId: number): Promise<Source> {
  const response = await api.post<Source>(`/sources/${sourceId}/watch/start`)
  return response.data
}

export async function stopSourceWatch(sourceId: number): Promise<Source> {
  const response = await api.post<Source>(`/sources/${sourceId}/watch/stop`)
  return response.data
}

export async function listImportJobs(limit = 50): Promise<ImportJob[]> {
  const response = await api.get<ImportJob[]>('/import-jobs', { params: { limit } })
  return response.data
}

export async function listPhotos(limit = 60): Promise<Photo[]> {
  const response = await api.get<Photo[]>('/photos', { params: { limit } })
  return response.data
}

export async function listVideos(limit = 60): Promise<Video[]> {
  const response = await api.get<Video[]>('/videos', { params: { limit } })
  return response.data
}

export async function getPhoto(photoId: number): Promise<Photo> {
  const response = await api.get<Photo>(`/photos/${photoId}`)
  return response.data
}

export async function getVideo(videoId: number): Promise<Video> {
  const response = await api.get<Video>(`/videos/${videoId}`)
  return response.data
}

export async function reanalyzePhoto(photoId: number): Promise<Photo> {
  const response = await api.post<Photo>(`/photos/${photoId}/reanalyze`)
  return response.data
}

export async function findSimilarPhotos(photoId: number, limit = 24): Promise<SearchResponse> {
  const response = await api.get<SearchResponse>(`/photos/${photoId}/similar`, {
    params: { limit },
  })
  return response.data
}

export async function searchByImage(file: File, limit = 24): Promise<SearchResponse> {
  const formData = new FormData()
  formData.set('file', file)
  formData.set('limit', String(limit))
  const response = await api.post<SearchResponse>('/search/by-image', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

export async function searchByPersonImage(file: File, limit = 24): Promise<SearchResponse> {
  const formData = new FormData()
  formData.set('file', file)
  formData.set('limit', String(limit))
  const response = await api.post<SearchResponse>('/search/by-person-image', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

export async function searchPhotos(payload: SearchQueryPayload): Promise<SearchResponse> {
  const response = await api.post<SearchResponse>('/search', payload)
  return response.data
}

export async function searchVideos(payload: SearchQueryPayload): Promise<VideoSearchResponse> {
  const response = await api.post<VideoSearchResponse>('/search/videos', payload)
  return response.data
}

export async function listFaceClusters(limit = 50): Promise<FaceCluster[]> {
  const response = await api.get<FaceCluster[]>('/face-clusters', { params: { limit } })
  return response.data
}

export async function renameFaceCluster(
  clusterLabel: string,
  displayName: string,
): Promise<FaceCluster> {
  const response = await api.post<FaceCluster>(`/face-clusters/${clusterLabel}/rename`, {
    display_name: displayName,
  })
  return response.data
}

export async function listPeople(limit = 100): Promise<PersonProfile[]> {
  const response = await api.get<PersonProfile[]>('/people', { params: { limit } })
  return response.data
}

export async function createPerson(name: string): Promise<PersonProfile> {
  const response = await api.post<PersonProfile>('/people', { name })
  return response.data
}

export async function renamePerson(personId: number, name: string): Promise<PersonProfile> {
  const response = await api.post<PersonProfile>(`/people/${personId}/rename`, { name })
  return response.data
}

export async function deletePerson(personId: number): Promise<void> {
  await api.delete(`/people/${personId}`)
}

export async function listPersonSamples(personId: number): Promise<PersonSample[]> {
  const response = await api.get<PersonSample[]>(`/people/${personId}/samples`)
  return response.data
}

export async function addPersonSample(personId: number, file: File): Promise<PersonProfile> {
  const formData = new FormData()
  formData.set('file', file)
  const response = await api.post<PersonProfile>(`/people/${personId}/samples`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

export async function deletePersonSample(
  personId: number,
  sampleId: number,
): Promise<PersonProfile> {
  const response = await api.delete<PersonProfile>(`/people/${personId}/samples/${sampleId}`)
  return response.data
}

export async function listPhotosByPerson(personId: number, limit = 48): Promise<SearchResponse> {
  const response = await api.get<SearchResponse>(`/people/${personId}/photos`, {
    params: { limit },
  })
  return response.data
}

export async function listPersonCorrectionCandidates(
  personId: number,
  limit = 80,
): Promise<PersonClusterCorrectionCandidate[]> {
  const response = await api.get<PersonClusterCorrectionCandidate[]>(
    `/people/${personId}/correction-candidates`,
    {
      params: { limit },
    },
  )
  return response.data
}

export async function applyPersonClusterCorrection(
  personId: number,
  action: 'bind' | 'unbind',
  clusterLabels: string[],
): Promise<PersonClusterCorrectionResult> {
  const response = await api.post<PersonClusterCorrectionResult>(
    `/people/${personId}/cluster-corrections`,
    {
      action,
      cluster_labels: clusterLabels,
    },
  )
  return response.data
}

export async function listPhotosByFaceCluster(
  clusterLabel: string,
  limit = 48,
): Promise<SearchResponse> {
  const response = await api.get<SearchResponse>(`/face-clusters/${clusterLabel}/photos`, {
    params: { limit },
  })
  return response.data
}

export async function findSimilarVideos(videoId: number, limit = 24): Promise<VideoSearchResponse> {
  const response = await api.get<VideoSearchResponse>(`/videos/${videoId}/similar`, {
    params: { limit },
  })
  return response.data
}

export async function searchByVideo(file: File, limit = 24): Promise<VideoSearchResponse> {
  const formData = new FormData()
  formData.set('file', file)
  formData.set('limit', String(limit))
  const response = await api.post<VideoSearchResponse>('/search/videos/by-video', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

export async function searchVideosByPersonImage(
  file: File,
  limit = 24,
): Promise<VideoSearchResponse> {
  const formData = new FormData()
  formData.set('file', file)
  formData.set('limit', String(limit))
  const response = await api.post<VideoSearchResponse>(
    '/search/videos/by-person-image',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  )
  return response.data
}

export function getPhotoAssetUrl(photoId: number): string {
  return `${apiBaseUrl}/photos/${photoId}/asset`
}

export function getVideoAssetUrl(videoId: number): string {
  return `${apiBaseUrl}/videos/${videoId}/asset`
}

export function getVideoThumbnailUrl(videoId: number): string {
  return `${apiBaseUrl}/videos/${videoId}/thumbnail`
}

export function getPersonSampleAssetUrl(sampleId: number): string {
  return `${apiBaseUrl}/person-samples/${sampleId}/asset`
}

export async function getFaceTuning(): Promise<FaceTuningBundle> {
  const response = await api.get<FaceTuningBundle>('/face-tuning')
  return response.data
}

export async function previewFaceTuning(payload: FaceThresholds): Promise<FaceTuningBundle> {
  const response = await api.post<FaceTuningBundle>('/face-tuning/preview', {
    ...payload,
    rebuild_index: false,
  })
  return response.data
}

export async function saveFaceTuning(
  payload: FaceThresholds,
  rebuildIndex = false,
): Promise<FaceTuningBundle> {
  const response = await api.post<FaceTuningBundle>('/face-tuning/settings', {
    ...payload,
    rebuild_index: rebuildIndex,
  })
  return response.data
}
