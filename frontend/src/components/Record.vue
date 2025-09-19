<template>
  <div>
    <el-button type="primary" @click="startRecording" :disabled="isRecording">开始录音</el-button>
    <el-button type="danger" @click="stopRecording" :disabled="!isRecording">停止录音</el-button>
  </div>
  <br>
  <div style="text-align: left;width:1000px;background-color: blanchedalmond;margin:0 auto;">
    <div v-for="item in RecTexts">{{ item }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'

const isRecording = ref(false)
let audioContext: AudioContext
let sourceNode: MediaStreamAudioSourceNode
let scriptNode: ScriptProcessorNode
let sessionId = ''

const RecResult = ref("")
const RecTexts = ref<string[]>([])
RecTexts.value.push("")
// PCM 配置（需与后端一致）
const SAMPLE_RATE = 16000
const CHANNELS = 1
const BUFFER_SIZE = 2048 // 每次发送的采样数

// 初始化录音
const startRecording = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    // 创建录音会话
    const response = await axios.post('http://127.0.0.1:8000/start_recording')
    sessionId = response.data.session_id
    
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE })
    sourceNode = audioContext.createMediaStreamSource(stream)
    
    // 创建 PCM 处理器
    scriptNode = audioContext.createScriptProcessor(BUFFER_SIZE, CHANNELS, CHANNELS)
    scriptNode.onaudioprocess = (e) => {
      const pcmData = e.inputBuffer.getChannelData(0);
      // 转换为 16-bit 小端字节序的 ArrayBuffer
      const int16Buffer = new Int16Array(pcmData.map(v => Math.max(-1, Math.min(1, v)) * 0x7FFF));
      const arrayBuffer = int16Buffer.buffer.slice(0); // 创建一个新的 ArrayBuffer 副本

      // 使用 Blob 对象发送二进制数据
      const blob = new Blob([new DataView(arrayBuffer)], { type: 'application/octet-stream' });
      const formData = new FormData();
      formData.append('data', blob, 'audio_chunk'); // 可以给文件一个名字，但后端通常忽略它
      sendAudioChunk(formData, sessionId);
    }
    
    sourceNode.connect(scriptNode)
    scriptNode.connect(audioContext.destination)
    isRecording.value = true
  } catch (err) {
    console.error('录音失败:', err)
  }
}

// 发送音频块到后端
const sendAudioChunk = async (formData: FormData, sessionId: string) => {
  try {
    let res = await axios.post(`http://127.0.0.1:8000/upload_audio/${sessionId}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data' // 确保设置正确的 Content-Type
      }
    });
    console.log(res.data.results)
    if (res.data.results.length >0) {
      RecResult.value = res.data.results[0]
      if (RecResult.value.length < RecTexts.value[RecTexts.value.length-1].length) {
        RecTexts.value.push(RecResult.value)
      } else {
        RecTexts.value[RecTexts.value.length-1] = res.data.results[0]
      }
    }
  } catch (err) {
    console.error('上传失败:', err);
  }
}

// 停止录音
const stopRecording = async () => {
  scriptNode?.disconnect()
  sourceNode?.disconnect()
  let res = await axios.post(`http://127.0.0.1:8000/stop_recording/${sessionId}`)
  if (res.data.results.length >0) {
      RecResult.value = res.data.results[res.data.results.length-1]
    }
  isRecording.value = false
  sessionId = ''
}
</script>