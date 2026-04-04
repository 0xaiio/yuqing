import axios from 'axios'

import type {
  CreateSourcePayload,
  FaceCluster,
  HealthStatus,
  ImportJob,
  PersonProfile,
  PersonSample,
  Photo,
  SearchQueryPayload,
  SearchResponse,
  Source,
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

export async function getPhoto(photoId: number): Promise<Photo> {
  const response = await api.get<Photo>(`/photos/${photoId}`)
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

export async function listPhotosByPerson(personId: number, limit = 48): Promise<SearchResponse> {
  const response = await api.get<SearchResponse>(`/people/${personId}/photos`, {
    params: { limit },
  })
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

export function getPhotoAssetUrl(photoId: number): string {
  return `${apiBaseUrl}/photos/${photoId}/asset`
}

export function getPersonSampleAssetUrl(sampleId: number): string {
  return `${apiBaseUrl}/person-samples/${sampleId}/asset`
}
